import asyncio
import json
import os
import tempfile

import pytest

from event_replay import EventReplay


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
async def test_replay_raises_when_file_missing():
    missing_path = 'data/does_not_exist.json'
    if os.path.exists(missing_path):
        os.remove(missing_path)

    replay = EventReplay(missing_path)
    queue = asyncio.Queue()

    with pytest.raises(FileNotFoundError):
        await replay.replay(queue, delay=0.0)
