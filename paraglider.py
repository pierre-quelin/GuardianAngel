from blinker import signal
from transitions import Machine
from logger import get_logger
import asyncio
from datetime import datetime, timezone

DEFAULT_STATE_MACHINE = {
    'max_track_age_s': 300,
    'unknown_timeout_s': 300,
    'disconnected_timeout_s': 300,
    'clearance_timeout_s': 300,
    'alert_repeat_timeout_s': 300,
    'stopped_speed_mps': 0.56,
    'flying_speed_mps': 2.78,
    'high_speed_mps': 16.67,
    'clearance_max_agl_m': 60,
    'avg_speed_window_min': 5,
}


class Paraglider:
    states = [
        'Initial', 'Unknown', 'Flying', 'Clearance', 'Landed', 'Disconnected', 'Alert'
    ]

    def __init__(self, cfg, emit_signals=True, initialize=True):
        self.name = cfg.get('name')
        self.puretrack_key = cfg.get('puretrack_key')
        self.discord_user_id = cfg.get('discord_user_id')
        self.phone_number = cfg.get('phone_number')
        self.email = cfg.get('email')
        sm = dict(DEFAULT_STATE_MACHINE)
        sm.update(cfg.get('state_machine') or {})
        self._sm = sm

        self._last_datetime = None
        self._coordinates = (0.0, 0.0)
        self._course = 0.0
        self._altitude_gnd_calc = 0.0
        self._speed = 0.0
        self._avg_speed = 0.0

        self._logger = get_logger(self.name)
        self._emit_signals = False
        self._initialization_completed = False
        self._cleaned_up = False
        self._defer_initialization = not emit_signals
        self._machine = Machine(
            model=self,
            states=Paraglider.states,
            initial='Initial',
            ignore_invalid_triggers=True,
            on_exception='ignore',
        )
        self._timer = None
        self._pending_timer_duration = None
        self.alert = signal('alert')
        self.clearance = signal('clearance')
        self.takeoff = signal('takeoff')

        self._machine.add_transition(trigger='init', source='Initial', dest='Unknown')
        self._machine.add_transition(trigger='timeout', source='Disconnected', dest='Alert')
        self._machine.add_transition(trigger='timeout', source='Unknown', dest='Alert')
        self._machine.add_transition(trigger='landingConfirmed', source='Alert', dest='Landed')
        self._machine.add_transition(trigger='timeout', source='Alert', dest='Alert')
        self._machine.add_transition(trigger='landingConfirmed', source='Clearance', dest='Landed')
        self._machine.add_transition(trigger='timeout', source='Clearance', dest='Alert')

        # tick() order is priority. Two explicit Flying -> Clearance exits.
        self._machine.add_transition(
            trigger='tick', source='Flying', dest='Clearance',
            conditions=['has_recent_data', 'is_stopped', 'is_near_ground'],
        )
        self._machine.add_transition(
            trigger='tick', source='Flying', dest='Clearance',
            conditions=['has_recent_data', 'is_avg_stopped', 'is_near_ground'],
        )
        self._machine.add_transition(
            trigger='tick', source='Flying', dest='Alert',
            conditions=['has_recent_data', 'is_high_speed'],
        )
        self._machine.add_transition(
            trigger='tick', source='Flying', dest='Disconnected',
            conditions='is_disconnected',
        )
        self._machine.add_transition(
            trigger='tick', source='Landed', dest='Flying',
            conditions='is_flying',
        )
        self._machine.add_transition(
            trigger='tick', source='Landed', dest='Disconnected',
            conditions='is_disconnected',
        )
        self._machine.add_transition(
            trigger='tick', source='Unknown', dest='Flying',
            conditions='is_flying',
        )
        self._machine.add_transition(
            trigger='tick', source='Unknown', dest='Disconnected',
            conditions='is_disconnected',
        )
        self._machine.add_transition(
            trigger='tick', source='Unknown', dest='Landed',
            conditions='has_recent_data', unless='is_flying',
        )
        self._machine.add_transition(
            trigger='tick', source='Disconnected', dest='Unknown',
            conditions='has_recent_data',
        )

        if initialize:
            self.initialize()

    def initialize(self):
        if self._defer_initialization and not self._initialization_completed:
            self._initialization_completed = False
            return

        self._run_initialization()

    def _run_initialization(self):
        if self._initialization_completed:
            return
        self.init()
        self._initialization_completed = True
        self._logger.info(f"Paraglider {self.name} created. State: {self.state}")

    def restore_state(self, state):
        """UML 2 deep history: skip Initial, restore substate, re-run its entry."""
        if state not in Paraglider.states or state == 'Initial':
            return False
        self.cancel_timer()
        self._machine.set_state(state, model=self)
        self._logger.info(f"Paraglider {self.name} state restored: {state}")
        enter = getattr(self, f'on_enter_{state}', None)
        if enter is not None:
            enter()
        return True

    def on_enter_Unknown(self):
        self._logger.info(f"Entry action for Unknown state for {self.name}")
        self.arm_timer(self._sm['unknown_timeout_s'])
        if self._last_datetime is not None:
            self.tick()

    def on_exit_Unknown(self):
        self.cancel_timer()

    def on_enter_Flying(self):
        self._logger.info(f"Entry action for Flying state for {self.name}")
        if self._emit_signals:
            self.takeoff.send(self, message='takeoff!')

    def on_enter_Clearance(self):
        self._logger.info(f"Entry action for Clearance state for {self.name}")
        if self._emit_signals:
            self.clearance.send(self, message="clearance!")
        self.arm_timer(self._sm['clearance_timeout_s'])

    def on_exit_Clearance(self):
        self._logger.info(f"Exit action for Clearance state for {self.name}")
        self.cancel_timer()

    def on_enter_Alert(self):
        self._logger.warning(f"Entry action for Alert state for {self.name}")
        if self._emit_signals:
            self.alert.send(self, message="alert!")
        self.arm_timer(self._sm['alert_repeat_timeout_s'])

    def on_enter_Disconnected(self):
        self._logger.warning(f"Entry action for Disconnected state for {self.name}")
        self.arm_timer(self._sm['disconnected_timeout_s'])

    def on_exit_Alert(self):
        self._logger.warning(f"Exit action for Alert state for {self.name}")
        self.cancel_timer()

    def on_exit_Disconnected(self):
        self.cancel_timer()

    @property
    def has_recent_data(self):
        if self._last_datetime is None:
            return False
        age = (datetime.now(timezone.utc) - self._last_datetime).total_seconds()
        return 0 <= age <= self._sm['max_track_age_s']

    @property
    def is_disconnected(self):
        return self._last_datetime is not None and not self.has_recent_data

    @property
    def is_flying(self):
        return self.has_recent_data and self._avg_speed > self._sm['flying_speed_mps']

    @property
    def is_stopped(self):
        return self._speed is not None and self._speed < self._sm['stopped_speed_mps']

    @property
    def is_avg_stopped(self):
        return self._avg_speed is not None and self._avg_speed < self._sm['stopped_speed_mps']

    @property
    def is_near_ground(self):
        return (
            self._altitude_gnd_calc is not None
            and self._altitude_gnd_calc < self._sm['clearance_max_agl_m']
        )

    @property
    def is_high_speed(self):
        return self._avg_speed is not None and self._avg_speed > self._sm['high_speed_mps']

    def update(self, last_state):
        """Write telemetry then let the state machine decide via tick()."""
        self._last_datetime = last_state.get('datetime', self._last_datetime)
        self._coordinates = last_state.get('coordinates', self._coordinates)
        self._course = last_state.get('course', self._course)
        self._altitude_gnd_calc = last_state.get('altitude_gnd_calc', self._altitude_gnd_calc)
        self._speed = last_state.get('speed', self._speed)
        self._avg_speed = last_state.get('avg_speed', self._avg_speed)

        self._logger.info(
            f"Updated {self.name}: Coordinates={self._coordinates}, "
            f"Course={self._course} °, Alt Gnd={self._altitude_gnd_calc} m, "
            f"Speed={self._speed*3.6:.2f} km/h, Avg Speed={self._avg_speed*3.6:.2f} km/h"
        )

        if self._last_datetime is None:
            self._logger.warning(f"No timestamp available yet for {self.name}; skipping state check.")
            return

        self.tick()

    def arm_timer(self, duration):
        """Schedule a timeout on the running asyncio loop (thread-safe with the state machine)."""
        self.cancel_timer()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._pending_timer_duration = duration
            return

        self._pending_timer_duration = None
        self._timer = loop.create_task(self._timer_coro(duration))

    async def _timer_coro(self, duration):
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            raise
        if not self._cleaned_up:
            self.timeout()

    def cancel_timer(self):
        self._pending_timer_duration = None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def schedule_pending_timer(self):
        """Arm any timer that was deferred because no event loop was running."""
        if self._pending_timer_duration is not None and self._timer is None and not self._cleaned_up:
            duration = self._pending_timer_duration
            self._pending_timer_duration = None
            self.arm_timer(duration)

    def enable_signals(self):
        if not self._initialization_completed:
            self._run_initialization()
        self._emit_signals = True
        if self.state == 'Clearance':
            self.clearance.send(self, message='clearance!')
            self.arm_timer(self._sm['clearance_timeout_s'])
        elif self.state == 'Alert':
            self.alert.send(self, message='alert!')
            self.arm_timer(self._sm['alert_repeat_timeout_s'])

    def cleanup(self):
        self._cleaned_up = True
        self.cancel_timer()
