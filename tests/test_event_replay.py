import asyncio
import json
import os
import tempfile

import pytest

import database as db
from guardian_angel import GuardianAngel
from event_replay import EventReplay
from logger import get_logger
from paraglider import Paraglider


@pytest.fixture
def replay_file():
    with tempfile.NamedTemporaryFile('w+', suffix='.json', delete=False) as handle:
        json.dump([
            {'timestamp': '2024-01-01T00:00:00', 'event': {'type': 'alert', 'payload': {'name': 'Pilot'}}},
        ], handle)
        path = handle.name
    yield path
    os.remove(path)


@pytest.mark.asyncio
async def test_replay_pushes_events(replay_file):
    replay = EventReplay(replay_file)
    queue = asyncio.Queue()
    await replay.replay(queue, delay=0.0, limit=1)
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_replay_dispatches_events_to_handler(replay_file):
    replay = EventReplay(replay_file)
    received = []

    async def handler(event):
        received.append(event)

    await replay.replay(asyncio.Queue(), delay=0.0, handler=handler)

    assert received == [{'type': 'alert', 'payload': {'name': 'Pilot'}}]


@pytest.mark.asyncio
async def test_replay_applies_captured_puretrack_event(tmp_path):
    db.init_db_engine({'url': f'sqlite:///{tmp_path / "replay.db"}'})
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._paragliders = []
    angel._event_queue = asyncio.Queue()
    angel._last_seen_state = {}

    paraglider = Paraglider({
        'name': 'Replay Pilot',
        'puretrack_key': 'X-replay',
        'discord_id': 0,
        'phone_number': '',
        'email': '',
    }, emit_signals=False, initialize=False)
    paraglider._run_initialization()
    angel._paragliders.append(paraglider)

    await angel.process_replay_event({
        'type': 'puretrack',
        'payload': {
            'key': 'X-replay',
            'response': {
                'tracks': [{
                    'count': 1,
                    'last': 'T1782500000,L45.0,G5.0,A500,C90,S0,V0,g400',
                    'points': ['T1782499990,L45.0,G5.0,A500,C90,S0,V0,g400'],
                }],
            },
        },
    })

    assert paraglider.state == 'Clearance'
    await asyncio.sleep(0)
    assert angel._event_queue.qsize() == 1
    assert (await angel._event_queue.get())['type'] == 'clearance'
    paraglider.cleanup()


@pytest.mark.asyncio
async def test_replay_raises_when_file_missing():
    missing_path = 'data/does_not_exist.json'
    if os.path.exists(missing_path):
        os.remove(missing_path)

    replay = EventReplay(missing_path)
    queue = asyncio.Queue()

    with pytest.raises(FileNotFoundError):
        await replay.replay(queue, delay=0.0)
