import asyncio
import json
import os
from datetime import datetime


class EventReplay:
    def __init__(self, storage_path='data/replay_events.json'):
        self.storage_path = storage_path

    def _ensure_storage(self):
        directory = os.path.dirname(self.storage_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def record(self, event):
        payload = {
            'timestamp': datetime.utcnow().isoformat(),
            'event': event,
        }
        self._ensure_storage()
        if os.path.exists(self.storage_path):
            with open(self.storage_path, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
        else:
            data = []
        data.append(payload)
        with open(self.storage_path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2)
        return payload

    def load(self):
        with open(self.storage_path, 'r', encoding='utf-8') as handle:
            return json.load(handle)

    async def replay(self, queue, delay=1.0, limit=None, storage_path=None):
        if storage_path is not None:
            self.storage_path = storage_path

        if not os.path.exists(self.storage_path):
            raise FileNotFoundError(f"Replay file not found: {self.storage_path}")

        events = self.load()
        if limit is not None:
            events = events[:limit]
        for item in events:
            await queue.put(item['event'])
            await asyncio.sleep(delay)
