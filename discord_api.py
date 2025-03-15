import discord
from discord.ext import commands
from config import Config

# Load configuration
config = Config()

TOKEN = config.get('TOKEN')
CHANNEL_ID = config.get('CHANNEL_ID')
DISCORD_USER_ID = config.get('DISCORD_USER_ID')
PURE_TRACK_GRP = config.get('PURE_TRACK_GRP')
PURE_TRACK_KEY = config.get('PURE_TRACK_KEY')

intents = discord.Intents.default()
intents.message_content = True  # TODO - ?

bot = commands.Bot(command_prefix='>', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')
    MINUTES = 5
    await post_message_to_channel(CHANNEL_ID, f'<@{DISCORD_USER_ID}> is on a suspicious break for {MINUTES} minutes. see [PureTrack](https://puretrack.io/?l=44.91038,5.19237&z=15&group={PURE_TRACK_GRP}&k={PURE_TRACK_KEY})')

async def post_message_to_channel(channel_id, message):
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(message)
    else:
        print(f"The channel ID {channel_id} was not found.")

# Bot launch
bot.run(TOKEN)