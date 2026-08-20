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

        self.msg_hello = "I'm connected. 🤓\nStay safe."
        self.msg_good_bye = "I'll be back soon... 🤓\nStay safe."
        self.msg_waiting_landing_confirmation = "🕵I've detected your landing 🏁. Is everything ok ❓" # 🦺⚠❓🏁👀
        self.msg_bye = "👍 Good luck, I wish you all the best. See you later 😉"
        self.msg_not_addressed = "👮 This message was not addressed to you! Thank you."

        # self.cmd_state = f"{member.mention} is flying. See [PureTrack](https://puretrack.io/?l=44.91038,5.19237&z=15&group={self.puretrack_grp})"
        # self.cmd_error = f'An error occurred while checking the user: {e}'

        # Stores messages awaiting reply
        self.landing_to_be_confirmed = {}
        self._pending_confirmation_events = asyncio.Queue()
        self._pending_confirmation_ttl = 300
        self._ready_event = asyncio.Event()

    async def on_ready(self):
        # TODO - for test - await self.post_message_to_channel(self.channel_id, self.msg_hello)
        self.logger.info(f"Discord bot connected as '{self.user}'")
        self._ready_event.set()

    async def on_message(self, message):
        # Ignore messages sent by the bot itself
        if message.author == self.user:
            return

        # Check if the message is a reply to a bot's message
        if message.reference and message.reference.resolved:
            ref_message = message.reference.resolved
            if ref_message.author == self.user:
                if ref_message.id in self.landing_to_be_confirmed:
                    if self.landing_to_be_confirmed[ref_message.id] == message.author.id:
                        if message.content.lower() in {"yes", "y", "oui", "o"}:
                            self.logger.info(f"User {message.author.name} replied to the specific message: {message.content}")

                            await self._pending_confirmation_events.put({
                                'type': 'landing_confirmed',
                                'discord_id': message.author.id,
                                'message': message.content,
                            })

                            # Respond to the user
                            await self.post_bye(message.author.id)
                            del self.landing_to_be_confirmed[ref_message.id] # remove from dictionary
                        else:
                            await self._pending_confirmation_events.put({
                                'type': 'landing_rejected',
                                'discord_id': message.author.id,
                                'message': message.content,
                            })
                            del self.landing_to_be_confirmed[ref_message.id]
                    else:
                        await self.post_not_addressed(message.author.id)

        # Process commands if the message is a command
        await self.process_commands(message)

    async def on_reaction_add(self, reaction, user):
        # Ignore reactions added by the bot itself
        if user == self.user:
            return

        # Check if the reaction is on the specific message
        self._cleanup_expired_confirmations()
        if reaction.message.id in self.landing_to_be_confirmed:
            if self.landing_to_be_confirmed[reaction.message.id]['discord_id'] == user.id:
                if str(reaction.emoji) in {"👍", "👌"}:
                    self.logger.info(f"User {user.name} reacted with {str(reaction.emoji)} to the specific message.")

                    await self._pending_confirmation_events.put({
                        'type': 'landing_confirmed',
                        'discord_id': user.id,
                        'message': str(reaction.emoji),
                    })

                    # Respond to the user
                    await self.post_bye(user.id)
                    del self.landing_to_be_confirmed[reaction.message.id] # remove from dictionary
                else:
                    pass # TODO - Alert ?
            else:
                await self.post_not_addressed(user.id)

    async def post_message_to_channel(self, channel_id, message):
        """Post a message to a specific channel."""
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except discord.DiscordException:
                self.logger.exception("Unable to fetch Discord channel %s", channel_id)
                return None
        if channel:
            msg = await channel.send(message)
            self.logger.info(f"Message '{message}' posted to channel {channel_id}")
            return msg.id
        else:
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



    async def post_waiting_landing_confirmation(self, discord_id):
        self.logger.info(f"post_waiting_landing_confirmation discord_id {discord_id}")
        msg_id = await self.post_message_to_channel(self.channel_id, f"<@{discord_id}> " + self.msg_waiting_landing_confirmation)
        self.landing_to_be_confirmed[msg_id] = {
            'discord_id': discord_id,
            'created_at': asyncio.get_running_loop().time(),
        }

    async def post_bye(self, discord_id):
        self.logger.info(f"post_bye discord_id {discord_id}")
        await self.post_message_to_channel(self.channel_id, f"<@{discord_id}> " + self.msg_bye)

    async def post_not_addressed(self, discord_id):
        self.logger.info(f"post_not_addressed discord_id {discord_id}")
        await self.post_message_to_channel(self.channel_id, f"<@{discord_id}> " + self.msg_not_addressed)

    async def setup_hook(self) -> None:
        self.add_command(echo)
        self.add_command(check)
        # create the background task and run it in the background
        # self._task = self.loop.create_task(self.my_background_task())
        pass

    async def process_pending_confirmations(self, callback):
        while True:
            event = await self._pending_confirmation_events.get()
            await callback(event)

    def _cleanup_expired_confirmations(self):
        current_time = asyncio.get_running_loop().time()
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
        await ctx.send(f"{member.mention} is flying. See [PureTrack](https://puretrack.io/?l=44.91038,5.19237&z=15&group={self.puretrack_grp})")
    except discord.HTTPException as e:
        await ctx.send(f'An error occurred while checking the user: {e}')
