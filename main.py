from config import Config
from logger import get_logger
# from guardian_angel import GuardianAngel
from discord_bot import DiscordBot


if __name__ == "__main__":
    logger = get_logger(__name__)
    cfg = Config()

    client = DiscordBot(cfg.get('guardian_angel').get('discord_bot'))
    client.run()
