from blinker import signal
from transitions import Machine
from logger import get_logger
import threading
from datetime import datetime, timezone

class Paraglider:
    states = [
        'Initial', 'Unknown', 'Flying', 'Clearance', 'Landed', 'Disconnected', 'Alert'
    ]

    def __init__(self, cfg, emit_signals=True, initialize=True):
        self.name = cfg.get('name')
        self.puretrack_key = cfg.get('puretrack_key')
        self.discord_id = cfg.get('discord_id')
        self.phone_number = cfg.get('phone_number')
        self.email = cfg.get('email')

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
        self.alert = signal('alert')
        self.clearance = signal('clearance')

        # Define transitions
        self._machine.add_transition(trigger='init', source='Initial', dest='Unknown')
        self._machine.add_transition(trigger='connected', source='Disconnected', dest='Unknown')
        self._machine.add_transition(trigger='timeout', source='Disconnected', dest='Alert')
        self._machine.add_transition(trigger='timeout', source='Unknown', dest='Alert')
        self._machine.add_transition(trigger='nullSpeed', source='Flying', dest='Clearance')
        self._machine.add_transition(trigger='highSpeed', source='Flying', dest='Alert')
        self._machine.add_transition(trigger='disconnected', source='Flying', dest='Disconnected')
        self._machine.add_transition(trigger='landingConfirmed', source='Alert', dest='Landed')
        self._machine.add_transition(trigger='timeout', source='Alert', dest='Alert')
        self._machine.add_transition(trigger='landingConfirmed', source='Clearance', dest='Landed')
        self._machine.add_transition(trigger='timeout', source='Clearance', dest='Alert')
        self._machine.add_transition(trigger='flying', source='Landed', dest='Flying')
        self._machine.add_transition(trigger='check', source='Unknown', dest='Flying', conditions='is_flying')
        self._machine.add_transition(trigger='check', source='Unknown', dest='Disconnected', conditions='is_disconnected')
        self._machine.add_transition(trigger='check', source='Unknown', dest='Landed', conditions='has_recent_data', unless='is_flying')

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
        if state not in Paraglider.states or state == 'Initial':
            return False
        self._machine.set_state(state, model=self)
        self._logger.info(f"Paraglider {self.name} state restored: {state}")
        return True

    def on_enter_Unknown(self):
        self._logger.info(f"Entry action for Unknown state for {self.name}")
        self.arm_timer(300)
        if self._last_datetime is not None:
            self.check()

    def on_exit_Unknown(self):
        self.cancel_timer()

    def on_enter_Clearance(self):
        self._logger.info(f"Entry action for Clearance state for {self.name}")
        if self._emit_signals:
            self.clearance.send(self, message="clearance!")
            self.arm_timer(300) # Arm a timer for 5 minutes

    def on_exit_Clearance(self):
        self._logger.info(f"Exit action for Clearance state for {self.name}")
        self.cancel_timer()

    def on_enter_Alert(self):
        self._logger.warning(f"Entry action for Alert state for {self.name}")
        if self._emit_signals:
            self.alert.send(self, message="alert!")
            self.arm_timer(300) # Arm a timer for 5 minutes

    def on_enter_Disconnected(self):
        self._logger.warning(f"Entry action for Disconnected state for {self.name}")
        self.arm_timer(300)

    def on_exit_Alert(self):
        self._logger.warning(f"Exit action for Alert state for {self.name}")
        self.cancel_timer()

    @property
    def is_flying(self):
        return self.has_recent_data and self._avg_speed > 2.78

    @property
    def has_recent_data(self):
        if self._last_datetime is None:
            return False
        age = (datetime.now(timezone.utc) - self._last_datetime).total_seconds()
        return 0 <= age <= 300

    @property
    def is_disconnected(self):
        return self._last_datetime is not None and not self.has_recent_data

    def update(self, last_state):
        """
        Update the paraglider's latest known values and adjust its state.

        Args:
            last_state (dict): A dictionary containing the latest known data for the paraglider,
                            including position, speed, altitude, etc.
        """
        # Update attributes with the latest known values
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

        if not self.has_recent_data:
            if self._last_datetime is None:
                self._logger.warning(f"No timestamp available yet for {self.name}; skipping state check.")
                return
            if self.state == 'Unknown':
                self.check()
            elif self.state in {'Flying', 'Landed'}:
                self.disconnected()
            return

        # Adjust the state based on the updated values
        if self._avg_speed > 16.67: # 60km/h or 16,67m/s
            self.highSpeed()
        elif self._avg_speed > 2.78: # 10km/h or 2,78m/s
            self.flying()
        elif (self._avg_speed < 0.56) and (self._altitude_gnd_calc < 60): # 2km/h or 0,56m/s
            self.nullSpeed()

        if self.state == 'Unknown' and self._last_datetime is not None:
            self.check()

        self.connected()


    def arm_timer(self, duration):
        self.cancel_timer()
        self._timer = threading.Timer(duration, self._timer_expired)
        self._timer.daemon = True
        self._timer.start()

    def _timer_expired(self):
        if not self._cleaned_up:
            self.timeout()

    def cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def enable_signals(self):
        if not self._initialization_completed:
            self._run_initialization()
        self._emit_signals = True
        if self.state == 'Clearance':
            self.clearance.send(self, message='clearance!')
            self.arm_timer(300)
        elif self.state == 'Alert':
            self.alert.send(self, message='alert!')
            self.arm_timer(300)

    def cleanup(self):
        self._cleaned_up = True
        self.cancel_timer()
