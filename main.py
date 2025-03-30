import time
from config import Config
from logger import get_logger
from guardian_angel import GuardianAngel

logger = get_logger(__name__)

def main():
    try:
        config = Config()
        #logger = Logger(cfg=config.get('logging'))
        guardian_angel = GuardianAngel(cfg=config.get('guardian_angel'))

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("Application stopped by user.")

if __name__ == "__main__":
    main()
