import asyncio
from datetime import datetime, timedelta, timezone
from types import MethodType, SimpleNamespace

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
        'discord_user_id': 123,
        'phone_number': '+33600000000',
        'email': 'test@example.com',
    }
    instance = Paraglider(cfg)
    yield instance
    instance.cleanup()


def test_initial_state(paraglider):
    assert paraglider.state == 'Unknown'


def test_persisted_state_can_be_restored(paraglider):
    assert paraglider.restore_state('Flying') is True
    assert paraglider.state == 'Flying'


def test_unknown_timeout_becomes_alert(paraglider):
    paraglider.timeout()
    assert paraglider.state == 'Alert'


def test_clearance_transition(paraglider):
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 100.0,
        'speed': 3.0,
        'avg_speed': 3.0,
    })
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 10.0,
        'speed': 0.1,
        'avg_speed': 0.1,
    })
    assert paraglider.state == 'Clearance'


def test_clearance_uses_instant_speed_not_avg_speed(paraglider):
    """Landing check must not wait for the 5-minute average to decay."""
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 100.0,
        'speed': 10.0,
        'avg_speed': 10.0,
    })
    assert paraglider.state == 'Flying'
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 3.0,
        'speed': 0.1,
        'avg_speed': 9.5,  # still high from recent flight
    })
    assert paraglider.state == 'Clearance'


def test_stale_track_goes_disconnected_not_clearance(paraglider):
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 100.0,
        'speed': 10.0,
        'avg_speed': 10.0,
    })
    assert paraglider.state == 'Flying'
    paraglider.update({
        'datetime': datetime.now(timezone.utc) - timedelta(seconds=301),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 3.0,
        'speed': 0.0,
        'avg_speed': 0.0,
    })
    assert paraglider.state == 'Disconnected'


def test_grey_zone_stays_flying(paraglider):
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 100.0,
        'speed': 10.0,
        'avg_speed': 10.0,
    })
    assert paraglider.state == 'Flying'
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 10.0,
        'speed': 1.0,
        'avg_speed': 1.5,
    })
    assert paraglider.state == 'Flying'


def test_clearance_via_avg_speed_when_instant_speed_not_stopped(paraglider):
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 100.0,
        'speed': 10.0,
        'avg_speed': 10.0,
    })
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 10.0,
        'speed': 1.0,
        'avg_speed': 0.1,
    })
    assert paraglider.state == 'Clearance'


def test_restore_disconnected_arms_watchdog(paraglider):
    assert paraglider.restore_state('Disconnected') is True
    assert paraglider.state == 'Disconnected'
    assert paraglider._pending_timer_duration == paraglider._sm['disconnected_timeout_s']


def test_restore_landed_does_not_emit_clearance():
    seen = []
    cfg = {
        'name': 'Landed Pilot',
        'puretrack_key': 'landed-key',
        'discord_user_id': 1,
        'phone_number': '',
        'email': '',
    }
    paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
    paraglider.clearance.connect(lambda sender, message: seen.append(message), weak=False)
    paraglider._run_initialization()
    paraglider.restore_state('Landed')
    paraglider.enable_signals()
    assert paraglider.state == 'Landed'
    assert seen == []
    paraglider.cleanup()


def test_landing_confirmation_transition(paraglider):
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 100.0,
        'speed': 3.0,
        'avg_speed': 3.0,
    })
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 10.0,
        'speed': 0.1,
        'avg_speed': 0.1,
    })
    paraglider.landingConfirmed()
    assert paraglider.state == 'Landed'


def test_guardian_angel_initializes_event_queue():
    cfg = Config()
    angel = GuardianAngel(cfg.get('guardian_angel'))
    assert hasattr(angel, '_event_queue')


def test_initial_landed_state_does_not_emit_clearance_after_registration():
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
    angel.on_takeoff = MethodType(lambda self, sender, message: None, angel)
    angel._last_seen_state = {}
    angel._state_machine_cfg = {}

    angel.add_paraglider({
        'name': 'Tam',
        'puretrack_key': 'tam-key',
        'discord_user_id': 123,
        'phone_number': '+33600000000',
        'email': 'tam@example.com',
    })

    assert seen == []


def test_unchanged_alert_snapshot_does_not_repeat_notification():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._event_queue = asyncio.Queue()
    angel._last_seen_state = {}

    cfg = {
        'name': 'Tam',
        'puretrack_key': 'tam-key',
        'discord_user_id': 123,
        'phone_number': '+33600000000',
        'email': 'tam@example.com',
    }
    paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
    paraglider._run_initialization()
    paraglider.restore_state('Alert')

    assert angel._queue_state_event_if_changed(paraglider) is True
    assert angel._queue_state_event_if_changed(paraglider) is False

    assert angel._event_queue.qsize() == 1
    assert angel._event_queue.get_nowait() == {
        'type': 'alert', 'payload': {'name': 'Tam'},
    }
    paraglider.cleanup()


def test_alert_signal_and_following_snapshot_queue_one_event():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._event_queue = asyncio.Queue()
    angel._last_seen_state = {}

    paraglider = Paraglider(
        {'name': 'Tam', 'puretrack_key': 'tam-key'},
        emit_signals=False,
        initialize=False,
    )
    paraglider._run_initialization()
    paraglider.cancel_timer()
    paraglider.alert.connect(angel.on_alert, weak=False)
    paraglider._emit_signals = True

    paraglider.timeout()
    angel._queue_state_event_if_changed(paraglider)

    assert angel._event_queue.qsize() == 1
    assert angel._event_queue.get_nowait() == {
        'type': 'alert', 'payload': {'name': 'Tam'},
    }
    paraglider.cleanup()


def test_remove_paraglider_works_by_name():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel._paragliders = []
    angel.logger = get_logger('test')
    angel.on_alert = MethodType(lambda self, sender, message: None, angel)
    angel.on_clearance = MethodType(lambda self, sender, message: None, angel)
    angel.on_takeoff = MethodType(lambda self, sender, message: None, angel)
    angel._last_seen_state = {}
    angel._state_machine_cfg = {}

    angel.add_paraglider({
        'name': 'Tam',
        'puretrack_key': 'tam-key',
        'discord_user_id': 123,
        'phone_number': '+33600000000',
        'email': 'tam@example.com',
    })

    angel.remove_paraglider('Tam')

    assert angel._paragliders == []


def test_takeoff_signal_on_enter_flying():
    seen = []
    cfg = {
        'name': 'Takeoff Pilot',
        'puretrack_key': 'takeoff-key',
        'discord_user_id': 1,
        'phone_number': '',
        'email': '',
    }
    paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
    paraglider.takeoff.connect(lambda sender, message: seen.append(message), weak=False)
    paraglider._run_initialization()
    paraglider.cancel_timer()
    paraglider._emit_signals = True
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 100.0,
        'speed': 10.0,
        'avg_speed': 10.0,
    })
    assert paraglider.state == 'Flying'
    assert seen == ['takeoff!']
    paraglider.cleanup()


def test_restore_flying_does_not_emit_takeoff_after_enable_signals():
    seen = []
    cfg = {
        'name': 'Restored Pilot',
        'puretrack_key': 'restore-fly-key',
        'discord_user_id': 1,
        'phone_number': '',
        'email': '',
    }
    paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
    paraglider.takeoff.connect(lambda sender, message: seen.append(message), weak=False)
    paraglider._run_initialization()
    paraglider.cancel_timer()
    paraglider.restore_state('Flying')
    paraglider.enable_signals()
    assert paraglider.state == 'Flying'
    assert seen == []
    paraglider.cleanup()


@pytest.mark.asyncio
async def test_takeoff_event_sends_discord_embed():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._stop_monitoring = asyncio.Event()
    angel._event_queue = asyncio.Queue()
    angel._replay = SimpleNamespace(record=lambda event: None)
    angel.puretrack_grp = 'test-group'
    sent = []

    async def send_message(message, notification_type=None):
        sent.append((message, notification_type))
        return 1

    angel.discord_bot = SimpleNamespace(send_message_async=send_message)
    paraglider = SimpleNamespace(
        name='Pilot',
        puretrack_key='X-pilot',
        discord_user_id=123,
    )
    angel._paragliders = [paraglider]
    angel.get_paraglider = lambda name: paraglider if name == 'Pilot' else None

    task = asyncio.create_task(angel._process_events())
    await angel._event_queue.put({'type': 'takeoff', 'payload': {'name': 'Pilot'}})
    await asyncio.sleep(0.05)
    angel._stop_monitoring.set()
    await task

    assert len(sent) == 1
    message, notification_type = sent[0]
    assert notification_type == 'takeoff'
    assert 'Pilot' in message
    assert '&k=X-pilot' in message
    assert 'group=' not in message


def test_takeoff_notification_style_title():
    from discord_bot import DiscordBot
    title, _color = DiscordBot._NOTIFICATION_STYLES['takeoff']
    assert title == 'TAKE OFF'


def test_shared_discord_user_confirms_the_targeted_paraglider():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._paragliders = []

    first = Paraglider({
        'name': 'First', 'puretrack_key': 'X-first', 'discord_user_id': 7,
        'phone_number': '', 'email': '',
    }, emit_signals=False, initialize=False)
    second = Paraglider({
        'name': 'Second', 'puretrack_key': 'X-second', 'discord_user_id': 7,
        'phone_number': '', 'email': '',
    }, emit_signals=False, initialize=False)
    first._run_initialization()
    second._run_initialization()
    for paraglider in (first, second):
        paraglider.update({
            'datetime': datetime.now(timezone.utc),
            'coordinates': (0.0, 0.0),
            'course': 0.0,
            'altitude_gnd_calc': 10.0,
            'speed': 0.1,
            'avg_speed': 0.1,
        })
    angel._paragliders.extend([first, second])

    angel._apply_confirmation_event({
        'type': 'landing_confirmed',
        'discord_id': 7,
        'paraglider_key': 'X-second',
    })

    assert first.state == 'Landed'
    assert second.state == 'Landed'
    first.cleanup()
    second.cleanup()


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
    angel._paragliders = []
    angel._fetch_remote_group_requested = False
    angel.puretrack_site_cfg = {'group': 'test-group'}
    angel.puretrack_grp = 'test-group'
    angel.discord_bot_cfg = {'bot_token': 'token', 'discord_channel_id': 123}
    angel._event_queue = asyncio.Queue()

    created = {}

    class DummyBot:
        def __init__(self, cfg):
            created['cfg'] = cfg

        async def send_shutdown_message(self):
            return None

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

    assert created['cfg']['bot_token'] == 'token'
    assert created['cfg']['discord_channel_id'] == 123
    assert created['cfg']['puretrack_group'] == 'test-group'


@pytest.mark.asyncio
async def test_alert_confirmation_targets_the_paraglider():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._stop_monitoring = asyncio.Event()
    angel._event_queue = asyncio.Queue()
    angel._replay = SimpleNamespace(record=lambda event: None)
    angel.puretrack_grp = 'test-group'
    paraglider = SimpleNamespace(
        name='Pilot',
        discord_user_id=123,
        puretrack_key='X-pilot',
        phone_number='',
        email='',
    )
    angel._paragliders = [paraglider]
    angel.discord_bot = SimpleNamespace()
    targeted = []
    plain = []

    async def post_confirmation(
        discord_id, message, paraglider_key, mention_first=True, notification_type=None
    ):
        targeted.append((discord_id, message, paraglider_key, mention_first, notification_type))

    async def send_message(message, notification_type=None):
        plain.append((message, notification_type))

    angel.discord_bot.post_waiting_landing_confirmation = post_confirmation
    angel.discord_bot.send_message_async = send_message

    task = asyncio.create_task(angel._process_events())
    await angel._event_queue.put({'type': 'alert', 'payload': {'name': 'Pilot'}})
    await asyncio.sleep(0.05)
    angel._stop_monitoring.set()
    await task

    assert targeted == [(
        123,
        '⚠️ Alert for [Pilot](https://puretrack.io/?l=44.91038,5.19237&z=15&k=X-pilot)',
        'X-pilot',
        False,
        'alert',
    )]
    assert plain == []


@pytest.mark.asyncio
async def test_clearance_dispatch_uses_clearance_notification_type():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._stop_monitoring = asyncio.Event()
    angel._event_queue = asyncio.Queue()
    angel._replay = SimpleNamespace(record=lambda event: None)
    angel.puretrack_grp = 'test-group'
    paraglider = SimpleNamespace(
        name='Pilot',
        discord_user_id=123,
        puretrack_key='X-pilot',
        phone_number='',
        email='',
    )
    angel._paragliders = [paraglider]
    angel.discord_bot = SimpleNamespace()
    sent = []

    async def post_confirmation(
        discord_id, message, paraglider_key, mention_first=True, notification_type=None
    ):
        sent.append((discord_id, message, paraglider_key, notification_type))

    angel.discord_bot.post_waiting_landing_confirmation = post_confirmation

    task = asyncio.create_task(angel._process_events())
    await angel._event_queue.put({'type': 'clearance', 'payload': {'name': 'Pilot'}})
    await asyncio.sleep(0.05)
    angel._stop_monitoring.set()
    await task

    assert len(sent) == 1
    discord_id, message, paraglider_key, notification_type = sent[0]
    assert discord_id == 123
    assert '[Pilot](https://puretrack.io/?l=44.91038,5.19237&z=15&k=X-pilot)' in message
    assert 'Is everything ok' in message
    assert paraglider_key == 'X-pilot'
    assert notification_type == 'clearance'


@pytest.mark.asyncio
async def test_asyncio_timer_triggers_timeout_on_event_loop():
    cfg = {
        'name': 'Timer Pilot',
        'puretrack_key': 'timer-key',
        'discord_user_id': 1,
        'phone_number': '',
        'email': '',
    }
    paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
    paraglider._run_initialization()
    paraglider.cancel_timer()
    assert paraglider.state == 'Unknown'

    paraglider.arm_timer(0.05)
    await asyncio.sleep(0.15)

    assert paraglider.state == 'Alert'
    paraglider.cleanup()


@pytest.mark.asyncio
async def test_alert_timer_reentry_queues_a_reminder_occurrence():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._event_queue = asyncio.Queue()
    angel._last_seen_state = {'timer-key': 'Alert'}

    paraglider = Paraglider(
        {'name': 'Timer Pilot', 'puretrack_key': 'timer-key'},
        emit_signals=False,
        initialize=False,
    )
    paraglider._run_initialization()
    paraglider.cancel_timer()
    paraglider.restore_state('Alert')
    paraglider.alert.connect(angel.on_alert, weak=False)
    paraglider._emit_signals = True
    paraglider.arm_timer(0.01)

    await asyncio.sleep(0.05)

    assert paraglider.state == 'Alert'
    assert angel._event_queue.qsize() == 1
    assert angel._event_queue.get_nowait() == {
        'type': 'alert', 'payload': {'name': 'Timer Pilot'},
    }
    paraglider.cleanup()


@pytest.mark.asyncio
async def test_cancelled_asyncio_timer_does_not_fire():
    cfg = {
        'name': 'Cancel Pilot',
        'puretrack_key': 'cancel-key',
        'discord_user_id': 1,
        'phone_number': '',
        'email': '',
    }
    paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
    paraglider._run_initialization()
    paraglider.cancel_timer()
    paraglider.arm_timer(0.2)
    paraglider.cancel_timer()
    await asyncio.sleep(0.3)

    assert paraglider.state == 'Unknown'
    paraglider.cleanup()


@pytest.mark.asyncio
async def test_timer_and_update_share_the_same_event_loop():
    cfg = {
        'name': 'Race Pilot',
        'puretrack_key': 'race-key',
        'discord_user_id': 1,
        'phone_number': '',
        'email': '',
    }
    paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
    paraglider._run_initialization()
    paraglider.cancel_timer()

    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 100.0,
        'speed': 3.0,
        'avg_speed': 3.0,
    })
    assert paraglider.state == 'Flying'

    paraglider.arm_timer(0.2)
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 10.0,
        'speed': 0.1,
        'avg_speed': 0.1,
    })
    assert paraglider.state == 'Clearance'

    await asyncio.sleep(0.05)
    assert paraglider.state in {'Clearance', 'Alert', 'Landed', 'Flying'}
    paraglider.cleanup()


@pytest.mark.asyncio
async def test_start_monitoring_awaits_previous_monitor_task():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._stop_monitoring = asyncio.Event()
    angel._event_task = None
    angel._discord_task = None
    angel._confirmation_task = None
    angel.discord_bot = SimpleNamespace()
    angel.discord_bot_cfg = None
    angel._paragliders = []
    angel._fetch_remote_group_requested = False
    angel._event_queue = asyncio.Queue()

    finished = asyncio.Event()

    async def long_monitor(period):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            finished.set()
            raise

    angel._monitor_loop = MethodType(lambda self, period: long_monitor(period), angel)
    angel._monitor_task = asyncio.create_task(long_monitor(0.01))
    await asyncio.sleep(0)

    await angel.start_monitoring(period=0.01)
    assert finished.is_set()
    await angel.stop_monitoring()


@pytest.mark.asyncio
async def test_landing_rejected_escalates_supervisor_alert():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._event_queue = asyncio.Queue()
    angel._last_seen_state = {}
    angel._paragliders = []

    paraglider = Paraglider({
        'name': 'Pilot',
        'puretrack_key': 'X-pilot',
        'discord_user_id': 7,
        'phone_number': '',
        'email': '',
    }, emit_signals=False, initialize=False)
    paraglider._run_initialization()
    paraglider.cancel_timer()
    paraglider.restore_state('Alert')
    angel._paragliders.append(paraglider)
    angel._last_seen_state['X-pilot'] = 'Alert'

    angel._apply_confirmation_event({
        'type': 'landing_rejected',
        'discord_id': 7,
        'paraglider_key': 'X-pilot',
    })

    assert paraglider.state == 'Alert'
    event = angel._event_queue.get_nowait()
    assert event['type'] == 'alert'
    assert event['payload']['reason'] == 'assistance_requested'
    paraglider.cleanup()


@pytest.mark.asyncio
async def test_assistance_alert_uses_assistance_notification_type():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._stop_monitoring = asyncio.Event()
    angel._event_queue = asyncio.Queue()
    angel._replay = SimpleNamespace(record=lambda event: None)
    angel.puretrack_grp = 'test-group'
    paraglider = SimpleNamespace(
        name='Pilot',
        discord_user_id=123,
        puretrack_key='X-pilot',
        phone_number='',
        email='',
    )
    angel._paragliders = [paraglider]
    angel.discord_bot = SimpleNamespace()
    targeted = []
    supervisor_messages = []

    async def post_confirmation(*args, **kwargs):
        targeted.append(args)

    async def send_message(message, notification_type=None):
        supervisor_messages.append((message, notification_type))

    angel.discord_bot.post_waiting_landing_confirmation = post_confirmation
    angel.discord_bot.send_message_async = send_message

    task = asyncio.create_task(angel._process_events())
    await angel._event_queue.put({
        'type': 'alert',
        'payload': {'name': 'Pilot', 'reason': 'assistance_requested'},
    })
    await asyncio.sleep(0.05)
    angel._stop_monitoring.set()
    await task

    assert targeted == []
    assert supervisor_messages == [(
        '🚨 Assistance requested for [Pilot]'
        '(https://puretrack.io/?l=44.91038,5.19237&z=15&k=X-pilot)',
        'assistance',
    )]


@pytest.mark.asyncio
async def test_alert_without_pilot_discord_id_still_registers_confirmation():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._stop_monitoring = asyncio.Event()
    angel._event_queue = asyncio.Queue()
    angel._replay = SimpleNamespace(record=lambda event: None)
    angel.puretrack_grp = 'test-group'
    paraglider = SimpleNamespace(
        name='Pilot',
        discord_user_id=None,
        puretrack_key='X-pilot',
        phone_number='',
        email='',
    )
    angel._paragliders = [paraglider]
    angel.discord_bot = SimpleNamespace()
    targeted = []
    plain = []

    async def post_confirmation(
        discord_id, message, paraglider_key, mention_first=True, notification_type=None
    ):
        targeted.append((discord_id, message, paraglider_key, mention_first, notification_type))

    async def send_message(message, notification_type=None):
        plain.append((message, notification_type))

    angel.discord_bot.post_waiting_landing_confirmation = post_confirmation
    angel.discord_bot.send_message_async = send_message

    task = asyncio.create_task(angel._process_events())
    await angel._event_queue.put({'type': 'alert', 'payload': {'name': 'Pilot'}})
    await asyncio.sleep(0.05)
    angel._stop_monitoring.set()
    await task

    assert targeted == [(
        None,
        '⚠️ Alert for [Pilot](https://puretrack.io/?l=44.91038,5.19237&z=15&k=X-pilot)',
        'X-pilot',
        False,
        'alert',
    )]
    assert plain == []


@pytest.mark.asyncio
async def test_admin_confirmation_persists_source_admin():
    angel = GuardianAngel.__new__(GuardianAngel)
    angel.logger = get_logger('test')
    angel._stop_monitoring = asyncio.Event()
    angel._paragliders = []
    angel.discord_bot = SimpleNamespace(
        pending_confirmation_events=asyncio.Queue(),
    )
    persisted = []

    paraglider = Paraglider({
        'name': 'Pilot',
        'puretrack_key': 'X-pilot',
        'discord_user_id': 7,
        'phone_number': '',
        'email': '',
    }, emit_signals=False, initialize=False)
    paraglider._run_initialization()
    paraglider.state = 'Alert'
    angel._paragliders = [paraglider]

    def persist(state_by_key, source='tracking'):
        persisted.append((dict(state_by_key), source))

    angel._persist_paraglider_states = persist

    task = asyncio.create_task(angel._handle_confirmation_events())
    await angel.discord_bot.pending_confirmation_events.put({
        'type': 'landing_confirmed',
        'discord_id': 99,
        'actor_role': 'admin',
        'paraglider_key': 'X-pilot',
    })
    await asyncio.sleep(0.05)
    angel._stop_monitoring.set()
    await task
    paraglider.cleanup()

    assert paraglider.state == 'Landed'
    assert persisted == [({'X-pilot': 'Landed'}, 'admin')]
