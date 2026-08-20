import asyncio
import sys

from config import Config
from event_replay import EventReplay
from guardian_angel import GuardianAngel
from logger import configure_logging, get_logger


def parse_runtime_options(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    replay_mode = '--replay' in args
    dry_run = '--dry-run' in args
    debug = '--debug' in args

    replay_file = None
    delay = 1.0
    limit = None
    for index, arg in enumerate(args):
        if arg == '--replay-file' and index + 1 < len(args):
            replay_file = args[index + 1]
        elif arg == '--delay' and index + 1 < len(args):
            try:
                delay = float(args[index + 1])
            except ValueError:
                pass
        elif arg == '--limit' and index + 1 < len(args):
            try:
                limit = int(args[index + 1])
            except ValueError:
                pass

    return {
        'replay_mode': replay_mode,
        'dry_run': dry_run,
        'debug': debug,
        'replay_file': replay_file,
        'delay': delay,
        'limit': limit,
    }


async def main():
    options = parse_runtime_options()
    configure_logging(level='DEBUG' if options['debug'] else None)
    logger = get_logger(__name__)
    cfg = Config()

    if options['debug']:
        logger.info("Debug mode enabled")

    angel = GuardianAngel(
        cfg.get('guardian_angel'),
        fetch_remote_group=not options['replay_mode'],
    )
    if options['replay_mode']:
        logger.info("Replay mode enabled")
        replay = EventReplay(options['replay_file'] or 'data/replay_events.json')
        if options['dry_run']:
            logger.info("Dry run enabled: replaying events without sending Discord notifications")
            angel.discord_bot = None
        angel._stop_monitoring.clear()
        angel._event_task = asyncio.create_task(angel._process_events())
        try:
            await replay.replay(
                angel._event_queue,
                delay=options['delay'],
                limit=options['limit'],
                storage_path=options['replay_file'],
                handler=angel.process_replay_event,
            )
            await angel._event_queue.join()
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
