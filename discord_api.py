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
intents.reactions = True

bot = commands.Bot(command_prefix='>', intents=intents)

specific_message_id = None # test

@bot.event
async def on_ready():
    global specific_message_id # TODO - Declare that we are modifying the global variable
    logger.info(f"Virtual Guardian Angel connected as '{bot.user}'")

    await post_message_to_channel(channel_id, f"I'm connected. 🤓\nStay safe.")
    specific_message_id = await post_message_to_channel(channel_id, f"<@{paraglider_discord_id}> 🕵I've detected your landing. 🏁 Is everything ok?") # 🦺⚠❓🏁


@bot.event
async def on_message(message):
    global specific_message_id # TODO - Declare that we are modifying the global variable
    # Ignore messages sent by the bot itself
    if message.author == bot.user:
        return

    # Check if the message is a reply to a bot's message
    if message.reference and message.reference.resolved:
        ref_message = message.reference.resolved
        if ref_message.author == bot.user:
            if ref_message.id == specific_message_id:
                if message.author.id == paraglider_discord_id:
                    logger.info(f"User {message.author.name} replied to the specific message: {message.content}")
                    if message.content.lower() in {"yes", "y", "oui", "o"}:
                        # Respond to the user
                        await message.channel.send(f"<@{message.author.id}> 👍 Good luck, I wish you all the best. See you later 😉")
                        specific_message_id = None # Reset the specific message ID
                    else:
                        pass # TODO
                else:
                    await message.channel.send(f"<@{message.author.id}> 👮 This message was not addressed to you! Thank you.")


    # Process commands if the message is a command
    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    global specific_message_id # TODO - Declare that we are modifying the global variable
    # Ignore reactions added by the bot itself
    if user == bot.user:
        return

    # Check if the reaction is on the specific message
    if reaction.message.id == specific_message_id:
        if user.id == paraglider_discord_id:
            if str(reaction.emoji) in {"👍", "👌"}:
                logger.info(f"User {user.name} reacted with {str(reaction.emoji)} to the specific message.")
                # Respond to the user
                await reaction.message.channel.send(f"<@{paraglider_discord_id}> 👍 Good luck, I wish you all the best. See you later 😉")
                specific_message_id = None # Reset the specific message ID
            else:
                pass # TODO
        else:
            await reaction.message.channel.send(f"<@{user.id}> 👮 This message was not addressed to you! Thank you.")

@bot.command()
async def echo(ctx, *, message: str):
    await ctx.send(message)

@bot.command()
async def check(ctx, *, member: discord.Member = None):
    try:
        await ctx.send(f"{member.mention} is flying. See [PureTrack](https://puretrack.io/?l=44.91038,5.19237&z=15&group={puretrack_grp}&k={paraglider_puretrack_key})")
    except discord.HTTPException as e:
        await ctx.send(f'An error occurred while checking the user: {e}')
        logger.error(f'An error occurred while checking the user: {e}')

async def post_message_to_channel(channel_id, message):
    channel = bot.get_channel(channel_id)
    if channel:
        msg = await channel.send(message)
        logger.info(f"Message '{message}' msg.id: {msg.id} posted to channel {channel_id}")
        return msg.id
    else:
        logger.error(f"The channel ID {channel_id} was not found.")
    return None

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
