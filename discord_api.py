import discord
from discord.ext import commands
from config import config

discord_cfg = config.get('discord')
bot_token = discord_cfg.get('bot_token')
channel_id = discord_cfg.get('channel_id')

# user.get('discord_user_id')
DISCORD_USER_ID = config.get('DISCORD_USER_ID')
# user.get('puretrack_grp')

PURE_TRACK_GRP = config.get('PURE_TRACK_GRP')
# user.get('puretrack_key')
PURE_TRACK_KEY = config.get('PURE_TRACK_KEY')

intents = discord.Intents.default()
intents.message_content = True  # TODO - ?

bot = commands.Bot(command_prefix='>', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')
    MINUTES = 5
    await post_message_to_channel(channel_id, f'<@{DISCORD_USER_ID}> is on a suspicious break for {MINUTES} minutes. see [PureTrack](https://puretrack.io/?l=44.91038,5.19237&z=15&group={PURE_TRACK_GRP}&k={PURE_TRACK_KEY})')

async def post_message_to_channel(channel_id, message):
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(message)
    else:
        print(f"The channel ID {channel_id} was not found.")

# Bot launch
bot.run(bot_token)