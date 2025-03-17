from config import config
import discord
from discord.ext import commands # bot
from logger import get_logger
import requests # post

logger = get_logger(__name__)

discord_cfg = config.get('discord')
bot_token = discord_cfg.get('bot_token')
channel_id = discord_cfg.get('channel_id')

puretrack_cfg = config.get('puretrack')
puretrack_grp = puretrack_cfg.get('group')

# user.get('puretrack_key')
paragliders_cfg = config.get('paragliders')
paraglider_puretrack_key = first_key = next(iter(paragliders_cfg), None) # todo
paraglider_discord_id = paragliders_cfg.get(paraglider_puretrack_key).get('discord_id')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='>', intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Virtual Guardian Angel connected as '{bot.user}'")

    await post_message_to_channel(channel_id, f"I'm connected. :nerd:\nStay safe.")
    #pass
    # print(f'Guardian Angel connected as {bot.user}')
    # MINUTES = 5
    # await post_message_to_channel(channel_id, f'<@{paraglider_discord_id}> is on a suspicious break for {MINUTES} minutes. see [PureTrack](https://puretrack.io/?l=44.91038,5.19237&z=15&group={puretrack_grp}&k={paraglider_puretrack_key})')

@bot.command()
async def echo(ctx, *, message: str):
    await ctx.send(message)

@bot.command()
async def check(ctx, *, member: discord.Member = None):
    try:
        await ctx.send(f"{member.mention} is flying")
    except discord.HTTPException as e:
        await ctx.send(f'An error occurred while checking the user: {e}')
        logger.error(f'An error occurred while checking the user: {e}')

async def post_message_to_channel(channel_id, message):
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(message)
        logger.info(f"Message '{message}' posted to channel {channel_id}")
    else:
        logger.error(f"The channel ID {channel_id} was not found.")

async def check_user_exists(user_id: int) -> bool:
    try:
        user = await bot.fetch_user(user_id)
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException as e:
        logger.error(f'An error occurred while checking the user: {e}')
        return False

# Bot launch
bot.run(bot_token)


# def sendPost(message):
#     MINUTES = 5
#     # msg = f'<@{paraglider_discord_id}> is on a suspicious break for {MINUTES} minutes. see [PureTrack](https://puretrack.io/?l=44.91038,5.19237&z=15&group={puretrack_grp}&k={paraglider_puretrack_key})'
#     url = f'https://discord.com/api/v10/channels/{channel_id}/messages'
#     data = {
#         'content': message
#     }
#     headers = {
#         'Authorization': f'Bot {bot_token}',
#         'Content-Type': 'application/json'
#     }

#     try:
#         response = requests.post(url, headers=headers, json=data)

#         if response.status_code == 200:
#             logger.info("Message '{message}' sent successfully!")
#         else:
#             logger.error(f'Error sending message: {response.status_code} - {response.text}')
#     except Exception as e:
#         logger.error("Error sending message :", e)
