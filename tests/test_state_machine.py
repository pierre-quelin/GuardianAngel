import asyncio
from datetime import datetime, timezone
from types import MethodType

import pytest

from config import Config
from guardian_angel import GuardianAngel
from logger import get_logger
from paraglider import Paraglider


@pytest.fixture
def paraglider():
    cfg = {
        'name': 'Test Pilot',
        'puretrack_key': 'test-key',
        'discord_id': 123,
        'phone_number': '+33600000000',
        'email': 'test@example.com',
    }
    instance = Paraglider(cfg)
    yield instance
    instance.cleanup()


def test_initial_state(paraglider):
    assert paraglider.state == 'Clearance'


def test_clearance_transition(paraglider):
    paraglider.flying()
    paraglider._speed = 0.1
    paraglider._avg_speed = 0.1
    paraglider._altitude_gnd_calc = 10
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 10.0,
        'speed': 0.1,
        'avg_speed': 0.1,
    })
    assert paraglider.state == 'Clearance'


def test_landing_confirmation_transition(paraglider):
    paraglider.clearance.send(paraglider, message='clearance')
    paraglider.landingConfirmed()
    assert paraglider.state == 'Landed'


def test_guardian_angel_initializes_event_queue():
    cfg = Config()
    angel = GuardianAngel(cfg.get('guardian_angel'))
    assert hasattr(angel, '_event_queue')


def test_initial_clearance_signal_is_emitted_after_registration():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel._paragliders = []
    angel.logger = get_logger('test')
    angel._event_queue = asyncio.Queue()
    angel.discord_bot = None
    angel.puretrack_grp = 'test-group'
    seen = []

    def recording_on_clearance(self, sender, message):
        seen.append(sender.name in [paraglider.name for paraglider in self._paragliders])

    angel.on_clearance = MethodType(recording_on_clearance, angel)
    angel.on_alert = MethodType(lambda self, sender, message: None, angel)

    angel.add_paraglider({
        'name': 'Tam',
        'puretrack_key': 'tam-key',
        'discord_id': 123,
        'phone_number': '+33600000000',
        'email': 'tam@example.com',
    })

    assert seen == [True]


def test_state_events_are_not_repeated_for_unchanged_state():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._event_queue = asyncio.Queue()
    angel._last_seen_state = {}

    cfg = {
        'name': 'Tam',
        'puretrack_key': 'tam-key',
        'discord_id': 123,
        'phone_number': '+33600000000',
        'email': 'tam@example.com',
    }
    paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
    paraglider._run_initialization()

    angel._queue_state_event_if_changed(paraglider)
    angel._queue_state_event_if_changed(paraglider)

    assert angel._event_queue.qsize() == 1


def test_remove_paraglider_works_by_name():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel._paragliders = []
    angel.logger = get_logger('test')
    angel.on_alert = MethodType(lambda self, sender, message: None, angel)
    angel.on_clearance = MethodType(lambda self, sender, message: None, angel)

    angel.add_paraglider({
        'name': 'Tam',
        'puretrack_key': 'tam-key',
        'discord_id': 123,
        'phone_number': '+33600000000',
        'email': 'tam@example.com',
    })

    angel.remove_paraglider('Tam')

    assert angel._paragliders == []


@pytest.mark.asyncio
async def test_start_monitoring_uses_discord_configuration(monkeypatch):
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._stop_monitoring = asyncio.Event()
    angel._monitor_task = None
    angel._event_task = None
    angel._discord_task = None
    angel._confirmation_task = None
    angel.discord_bot = None
    angel.puretrack_site_cfg = {'group': 'test-group'}
    angel.discord_bot_cfg = {'bot_token': 'token', 'channel_id': 123}
    angel._event_queue = asyncio.Queue()

    created = {}

    class DummyBot:
        def __init__(self, cfg):
            created['cfg'] = cfg

        async def start_async(self):
            return None

    async def dummy_monitor(period):
        return None

    async def dummy_event_processor():
        while not angel._stop_monitoring.is_set():
            await asyncio.sleep(0.01)

    angel._monitor_loop = MethodType(lambda self, period: dummy_monitor(period), angel)
    angel._process_events = MethodType(lambda self: dummy_event_processor(), angel)
    angel._handle_confirmation_events = MethodType(lambda self: dummy_event_processor(), angel)

    monkeypatch.setattr('guardian_angel.DiscordBot', DummyBot)

    await angel.start_monitoring(period=0.01)
    await asyncio.sleep(0.01)
    await angel.stop_monitoring()

    assert created['cfg'] == angel.discord_bot_cfg
