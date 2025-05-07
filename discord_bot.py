import discord
from discord.ext import commands
from logger import get_logger # TODO
from blinker import signal
import threading

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
        self.bot_token = cfg.get('bot_token')
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

    async def on_ready(self):
        # TODO - for test - await self.post_message_to_channel(self.channel_id, self.msg_hello)
        self.logger.info(f"Discord bot connected as '{self.user}'")

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

                            # TODO - Inform the GuardianAngel
                            self.landing_confirmed.send(self, message="Landing confirmed!")

                            # Respond to the user
                            await self.post_bye(message.author.id)
                            del self.landing_to_be_confirmed[ref_message.id] # remove from dictionary
                        else:
                            pass # TODO
                    else:
                        await self.post_not_addressed(message.author.id)

        # Process commands if the message is a command
        await self.process_commands(message)

    async def on_reaction_add(self, reaction, user):
        # Ignore reactions added by the bot itself
        if user == self.user:
            return

        # Check if the reaction is on the specific message
        if reaction.message.id in self.landing_to_be_confirmed:
            if self.landing_to_be_confirmed[reaction.message.id] == user.id:
                if str(reaction.emoji) in {"👍", "👌"}:
                    self.logger.info(f"User {user.name} reacted with {str(reaction.emoji)} to the specific message.")

                    # TODO - Inform the GuardianAngel

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
        if channel:
            msg = await channel.send(message)
            self.logger.info(f"Message '{message}' posted to channel {channel_id}")
            return msg.id
        else:
            self.logger.error(f"The channel ID {channel_id} was not found.")
        return None



    async def post_waiting_landing_confirmation(self, discord_id):
        self.logger.info(f"post_waiting_landing_confirmation discord_id {discord_id}")
        msg_id = await self.post_message_to_channel(self.channel_id, f"<@{discord_id}> " + self.msg_waiting_landing_confirmation)
        self.landing_to_be_confirmed[msg_id] = discord_id

    async def post_bye(self, discord_id):
        self.logger.info(f"post_bye discord_id {discord_id}")
        await self.post_message_to_channel(self.channel_id, f"<@{discord_id}> " + self.msg_bye)

    async def post_not_addressed(self, discord_id):
        self.logger.info(f"post_not_addressed discord_id {discord_id}")
        await self.post_message_to_channel(self.channel_id, f"<@{discord_id}> " + self.msg_not_addressed)

    async def setup_hook(self) -> None:
        self.add_command(self.echo)
        self.add_command(self.check)
        # create the background task and run it in the background
        # self._task = self.loop.create_task(self.my_background_task())
        pass

    def run(self):
        """Run the bot using the token."""
        self.logger.info("Starting Discord bot...")
        super().run(self.bot_token)  # Use the token stored in the class



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
