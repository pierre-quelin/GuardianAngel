import asyncio
import sys

from config import Config
from event_replay import EventReplay
from guardian_angel import GuardianAngel
from logger import get_logger


async def main():
    logger = get_logger(__name__)
    cfg = Config()

    replay_mode = '--replay' in sys.argv
    dry_run = '--dry-run' in sys.argv

    replay_file = None
    delay = 1.0
    limit = None
    for index, arg in enumerate(sys.argv):
        if arg == '--replay-file' and index + 1 < len(sys.argv):
            replay_file = sys.argv[index + 1]
        elif arg == '--delay' and index + 1 < len(sys.argv):
            try:
                delay = float(sys.argv[index + 1])
            except ValueError:
                logger.warning("Invalid delay value, defaulting to 1.0")
        elif arg == '--limit' and index + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[index + 1])
            except ValueError:
                logger.warning("Invalid limit value, replaying all events")

    angel = GuardianAngel(cfg.get('guardian_angel'))
    if replay_mode:
        logger.info("Replay mode enabled")
        replay = EventReplay(replay_file or 'data/replay_events.json')
        if dry_run:
            logger.info("Dry run enabled: replaying events without sending Discord notifications")
            angel.discord_bot = None
        try:
            await replay.replay(angel._event_queue, delay=delay, limit=limit, storage_path=replay_file)
        except FileNotFoundError as exc:
            logger.error(str(exc))
            return
        await angel.stop_monitoring()
        return

    await angel.start_monitoring(period=30)

    try:
        while True:
            await asyncio.sleep(60)
    finally:
        await angel.stop_monitoring()


if __name__ == "__main__":
    asyncio.run(main())
