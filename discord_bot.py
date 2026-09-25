import asyncio
import os

import discord
from discord.ext import commands
from logger import get_logger

class DiscordBot(commands.Bot):
    def __init__(self, cfg):
        """
        Initialize the Discord bot.

        Args:
            cfg (dict): Configuration for the bot (e.g., token, channel ID).
        """

        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        super().__init__(command_prefix='>', intents=intents)

        self.cfg = cfg
        self.logger = get_logger("GuardianAngel")

        # Extract configuration
        self.bot_token = os.getenv('DISCORD_BOT_TOKEN') or cfg.get('bot_token')
        self.channel_id = cfg.get('channel_id')
        self.send_confirmation_dm = cfg.get('send_confirmation_dm', False)
        self.puretrack_grp = cfg.get('puretrack_group') or cfg.get('group')
        self._send_max_retries = int(cfg.get('send_max_retries', 3))
        self._send_base_backoff = float(cfg.get('send_base_backoff', 1.0))

        self.msg_hello = "I'm connected. 🤓\nStay safe."
        self.msg_good_bye = "I'll be back soon... 🤓\nStay safe."
        self.msg_confirmation_instructions = (
            "Please reply to this message:\n"
            "👍 = I am safe and have landed.\n"
            "👎 = I need assistance or I am not safe."
        )
        self.msg_waiting_landing_confirmation = self.msg_confirmation_instructions
        self.msg_bye = "✅ Thank you {mention}. Your response has been recorded."
        self.msg_negative_response = (
            "🚨 Your response indicates that you need assistance or are not safe. "
            "The alert remains active. The guardian has been notified."
        )
        self.msg_not_addressed = "This message was not addressed to you."
        self.msg_unrecognized_response = (
            "⚠️ {mention}, response not recognized. Please reply with 👍 if you are safe and have landed, "
            "or 👎 if you need assistance or are not safe."
        )

        # Stores messages awaiting reply: message_id -> confirmation dict
        self.landing_to_be_confirmed = {}
        self._pending_confirmation_events = asyncio.Queue()
        self._pending_confirmation_ttl = 300
        self._ready_event = asyncio.Event()
        self._startup_message_sent = False
        self._shutdown_message_sent = False
        self._ttl_cleanup_task = None
        self._positive_reaction_emojis = {"👍", "👌"}
        self._negative_reaction_emojis = {"👎"}

    _POSITIVE_REACTION_EMOJIS = frozenset({"👍", "👌"})
    _NEGATIVE_REACTION_EMOJIS = frozenset({"👎"})

    @staticmethod
    def _normalize_discord_id(value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _normalize_reaction_emoji(emoji):
        """Normalize Discord reaction forms (variation selectors, skin tones)."""
        text = str(emoji)
        text = text.replace("\ufe0f", "").replace("\ufe0e", "")
        for tone in ("🏻", "🏼", "🏽", "🏾", "🏿"):
            text = text.replace(tone, "")
        return text

    def _register_confirmation_message(self, message_id, confirmation):
        self.landing_to_be_confirmed[message_id] = confirmation
        confirmation.setdefault("message_ids", set()).add(message_id)

    def _remove_confirmation(self, confirmation):
        """Remove only message IDs belonging to this confirmation (not other pilots)."""
        message_ids = set(confirmation.get("message_ids") or [])
        for message_id, entry in list(self.landing_to_be_confirmed.items()):
            if entry is confirmation:
                message_ids.add(message_id)
        for message_id in message_ids:
            self.landing_to_be_confirmed.pop(message_id, None)
        confirmation["message_ids"] = set()

    @property
    def pending_confirmation_events(self):
        """Public queue of landing confirmation / rejection events."""
        return self._pending_confirmation_events

    async def on_ready(self):
        self.logger.info(f"Discord bot connected as '{self.user}'")
        self._ready_event.set()
        if self._ttl_cleanup_task is None or self._ttl_cleanup_task.done():
            self._ttl_cleanup_task = asyncio.create_task(self._ttl_cleanup_loop())
        if not self._startup_message_sent:
            await self.send_message_async(self.msg_hello)
            self._startup_message_sent = True

    async def _ttl_cleanup_loop(self):
        while not self.is_closed():
            try:
                self._cleanup_expired_confirmations()
            except Exception as exc:
                self.logger.exception("Confirmation TTL cleanup failed: %s", exc)
            await asyncio.sleep(30)

    async def send_shutdown_message(self):
        if self._shutdown_message_sent or not self.is_ready():
            return None
        message_id = await self.send_message_async(self.msg_good_bye)
        self._shutdown_message_sent = True
        return message_id

    async def on_message(self, message):
        # Ignore messages sent by the bot itself
        if message.author == self.user:
            return

        self._cleanup_expired_confirmations()

        # Check if the message is a reply to a bot's message
        if message.reference and message.reference.resolved:
            ref_message = message.reference.resolved
            if ref_message.author == self.user:
                confirmation = self.landing_to_be_confirmed.get(ref_message.id)
                if confirmation is not None:
                    author_id = self._normalize_discord_id(message.author.id)
                    expected_id = self._normalize_discord_id(confirmation.get('discord_id'))
                    if expected_id == author_id:
                        response = message.content.strip().lower()
                        if response in {"yes", "i am safe", "i am safe and have landed"}:
                            self.logger.info(f"User {message.author.name} replied to the specific message: {message.content}")

                            await self._pending_confirmation_events.put({
                                'type': 'landing_confirmed',
                                'discord_id': author_id,
                                'paraglider_key': confirmation.get('paraglider_key'),
                                'message': message.content,
                            })

                            # Respond to the user
                            await self.post_bye(author_id)
                            self._remove_confirmation(confirmation)
                        elif response in {"no", "i need assistance", "i am not safe"}:
                            await self._pending_confirmation_events.put({
                                'type': 'landing_rejected',
                                'discord_id': author_id,
                                'paraglider_key': confirmation.get('paraglider_key'),
                                'message': message.content,
                            })
                            await self.post_negative_acknowledgment(author_id)
                            self._remove_confirmation(confirmation)
                        else:
                            if self.channel_id is not None:
                                await self._post_unrecognized_response(
                                    author_id,
                                    confirmation,
                                )
                    else:
                        await self.post_not_addressed(author_id)

        # Process commands if the message is a command
        await self.process_commands(message)

    async def on_reaction_add(self, reaction, user):
        # Raw reaction events are handled by on_raw_reaction_add below.
        return

    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.user.id:
            return

        await self._handle_reaction_confirmation(
            payload.message_id,
            payload.user_id,
            str(payload.emoji),
            str(payload.user_id),
        )

    async def _handle_reaction_confirmation(self, message_id, user_id, emoji, user_name):
        self.logger.info("Reaction received: message=%s user=%s emoji=%s", message_id, user_id, emoji)
        self._cleanup_expired_confirmations()
        confirmation = self.landing_to_be_confirmed.get(message_id)
        if confirmation is None:
            self.logger.info("Reaction ignored: no pending confirmation for message %s", message_id)
            return

        user_id = self._normalize_discord_id(user_id)
        expected_id = self._normalize_discord_id(confirmation.get('discord_id'))
        if expected_id != user_id:
            await self.post_not_addressed(user_id)
            return

        normalized_emoji = self._normalize_reaction_emoji(emoji)
        positive = getattr(self, '_positive_reaction_emojis', None) or self._POSITIVE_REACTION_EMOJIS
        negative = getattr(self, '_negative_reaction_emojis', None) or self._NEGATIVE_REACTION_EMOJIS
        accepted = set(positive) | set(negative)
        if normalized_emoji not in accepted:
            if self.channel_id is not None:
                await self._post_unrecognized_response(user_id, confirmation)
            return

        is_positive = normalized_emoji in positive
        self.logger.info(
            "User %s %s message %s (paraglider_key=%s)",
            user_name,
            "confirmed landing for" if is_positive else "reported an unsafe situation for",
            message_id,
            confirmation.get('paraglider_key'),
        )
        await self._pending_confirmation_events.put({
            'type': 'landing_confirmed' if is_positive else 'landing_rejected',
            'discord_id': user_id,
            'paraglider_key': confirmation.get('paraglider_key'),
            'message': normalized_emoji,
        })
        if is_positive:
            await self.post_bye(user_id)
        else:
            await self.post_negative_acknowledgment(user_id)
        self._remove_confirmation(confirmation)

    async def _post_unrecognized_response(self, discord_id, confirmation):
        message_id = await self.post_message_to_channel(
            self.channel_id,
            self.msg_unrecognized_response.format(mention=f"<@{discord_id}>"),
        )
        if message_id is not None:
            self._register_confirmation_message(message_id, confirmation)

    async def _send_channel_message(self, channel, message):
        last_error = None
        for attempt in range(self._send_max_retries):
            try:
                msg = await channel.send(message)
                self.logger.info(f"Message '{message}' posted to channel {channel.id}")
                return msg.id
            except discord.HTTPException as exc:
                last_error = exc
                if exc.status == 429:
                    retry_after = getattr(exc, 'retry_after', None)
                    delay = float(retry_after) if retry_after is not None else (
                        self._send_base_backoff * (2 ** attempt)
                    )
                    self.logger.warning(
                        "Discord rate limited on channel %s; retrying in %.1fs",
                        channel.id,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                self.logger.exception("Discord HTTP error posting to channel %s", channel.id)
                return None
            except discord.DiscordException:
                self.logger.exception("Discord error posting to channel %s", channel.id)
                return None
        self.logger.error(
            "Giving up posting to channel %s after %s attempts: %s",
            channel.id,
            self._send_max_retries,
            last_error,
        )
        return None

    async def post_message_to_channel(self, channel_id, message):
        """Post a message to a specific channel with rate-limit retries."""
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except discord.DiscordException:
                self.logger.exception("Unable to fetch Discord channel %s", channel_id)
                return None
        if channel:
            return await self._send_channel_message(channel, message)
        self.logger.error(f"The channel ID {channel_id} was not found.")
        return None

    async def send_message_async(self, message):
        """Asynchronously send a message to the configured channel."""
        if self.channel_id is None:
            self.logger.warning("No channel configured for Discord bot")
            return None
        if not self.is_ready():
            try:
                await asyncio.wait_for(self._ready_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                self.logger.error("Discord bot did not become ready before sending message")
                return None
        self.logger.info("Attempting to post Discord message to channel %s: %s", self.channel_id, message)
        try:
            return await self.post_message_to_channel(self.channel_id, message)
        except Exception as exc:
            self.logger.exception("Discord send failed: %s", exc)
            return None



    async def post_waiting_landing_confirmation(
        self, discord_id, message=None, paraglider_key=None, mention_first=True
    ):
        self.logger.info(f"post_waiting_landing_confirmation discord_id {discord_id}")
        self._cleanup_expired_confirmations()
        content = message or self.msg_waiting_landing_confirmation
        if message:
            content = f"{content}\n\n{self.msg_confirmation_instructions}"
        message_ids = []

        if self.channel_id is not None:
            if not self.is_ready():
                try:
                    await asyncio.wait_for(self._ready_event.wait(), timeout=30)
                except asyncio.TimeoutError:
                    self.logger.error("Discord bot did not become ready before sending confirmation")
                    return None
            if discord_id and message and not mention_first:
                channel_content = (
                    f"{message}\n\n<@{discord_id}> {self.msg_confirmation_instructions}"
                )
            else:
                channel_content = f"<@{discord_id}> {content}" if discord_id else content
            channel_message_id = await self.post_message_to_channel(self.channel_id, channel_content)
            if channel_message_id is not None:
                message_ids.append(channel_message_id)

        if discord_id and getattr(self, 'send_confirmation_dm', False):
            try:
                user = self.get_user(discord_id) or await self.fetch_user(discord_id)
                direct_message = await user.send(content)
                message_ids.append(direct_message.id)
            except discord.DiscordException:
                self.logger.exception("Unable to send landing confirmation DM to %s", discord_id)

        created_at = asyncio.get_running_loop().time()
        confirmation = {
            'discord_id': self._normalize_discord_id(discord_id),
            'paraglider_key': paraglider_key,
            'created_at': created_at,
            'message_ids': set(),
        }
        for message_id in message_ids:
            self._register_confirmation_message(message_id, confirmation)
        return message_ids[0] if message_ids else None

    async def post_bye(self, discord_id):
        self.logger.info(f"post_bye discord_id {discord_id}")
        await self.post_message_to_channel(
            self.channel_id,
            self.msg_bye.format(mention=f"<@{discord_id}>"),
        )

    async def post_negative_acknowledgment(self, discord_id):
        self.logger.info(f"post_negative_acknowledgment discord_id {discord_id}")
        await self.post_message_to_channel(
            self.channel_id,
            f"<@{discord_id}> " + self.msg_negative_response,
        )

    async def post_not_addressed(self, discord_id):
        self.logger.info(f"post_not_addressed discord_id {discord_id}")
        await self.post_message_to_channel(self.channel_id, f"<@{discord_id}> " + self.msg_not_addressed)

    async def setup_hook(self) -> None:
        self.add_command(echo)
        self.add_command(check)

    async def close(self):
        if self._ttl_cleanup_task is not None and not self._ttl_cleanup_task.done():
            self._ttl_cleanup_task.cancel()
            try:
                await self._ttl_cleanup_task
            except asyncio.CancelledError:
                pass
            self._ttl_cleanup_task = None
        await super().close()

    async def process_pending_confirmations(self, callback):
        while True:
            event = await self._pending_confirmation_events.get()
            await callback(event)

    def _cleanup_expired_confirmations(self):
        try:
            current_time = asyncio.get_running_loop().time()
        except RuntimeError:
            return
        expired_messages = [
            message_id for message_id, entry in self.landing_to_be_confirmed.items()
            if isinstance(entry, dict)
            and isinstance(entry.get('created_at'), (int, float))
            and (current_time - entry['created_at']) > self._pending_confirmation_ttl
        ]
        for message_id in expired_messages:
            self.logger.info("Pending confirmation expired for message %s", message_id)
            del self.landing_to_be_confirmed[message_id]

    def run(self):
        """Run the bot using the token."""
        self.logger.info("Starting Discord bot...")
        super().run(self.bot_token)  # Use the token stored in the class

    async def start_async(self):
        """Start the bot in a way compatible with the main asyncio loop."""
        self.logger.info("Starting Discord bot asynchronously...")
        await self.start(self.bot_token)



@commands.command()
async def echo(ctx, *, message: str = "No message provided"):
    await ctx.send(message)

@commands.command()
async def check(ctx, *, member: discord.Member = None):
    try:
        if member is None:
            await ctx.send("Please mention a member to check.")
            return
        group = getattr(ctx.bot, 'puretrack_grp', None) or 'unknown'
        await ctx.send(
            f"{member.mention} is flying. See "
            f"[PureTrack](https://puretrack.io/?l=44.91038,5.19237&z=15&group={group})"
        )
    except discord.HTTPException as e:
        await ctx.send(f'An error occurred while checking the user: {e}')
