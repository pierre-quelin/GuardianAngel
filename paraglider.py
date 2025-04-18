from blinker import signal
from transitions import Machine
from logger import get_logger
import threading
from datetime import datetime, timezone

class Paraglider:
    states = [
        'Initial', 'Unknown', 'Flying', 'Clearance', 'Landed', 'Disconnected', 'Alert'
    ]

    def __init__(self, cfg):
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
        self._machine = Machine(model=self, states=Paraglider.states, initial='Initial', ignore_invalid_triggers=True)
        self._timer = None
        self.alert = signal('alert')
        self.clearance = signal('clearance')

        # Define transitions
        self._machine.add_transition(trigger='init', source='Initial', dest='Unknown')
        self._machine.add_transition(trigger='connected', source='Disconnected', dest='Unknown')
        self._machine.add_transition(trigger='timeout', source='Disconnected', dest='Alert')
        self._machine.add_transition(trigger='nullSpeed', source='Flying', dest='Clearance')
        self._machine.add_transition(trigger='highSpeed', source='Flying', dest='Alert')
        self._machine.add_transition(trigger='disconnected', source='Flying', dest='Disconnected')
        self._machine.add_transition(trigger='landingConfirmed', source='Alert', dest='Landed')
        self._machine.add_transition(trigger='timeout', source='Alert', dest='Alert')
        self._machine.add_transition(trigger='landingConfirmed', source='Clearance', dest='Landed')
        self._machine.add_transition(trigger='timeout', source='Clearance', dest='Alert')
        self._machine.add_transition(trigger='flying', source='Landed', dest='Flying')
        self._machine.add_transition(trigger='check', source='Unknown', dest='Flying', conditions='is_flying')
        self._machine.add_transition(trigger='check', source='Unknown', dest='Clearance', unless='is_flying')

        self.init() # on_enter_Unknown called
        self._logger.info(f"Paraglider {self.name} created. State: {self.state}")

    def on_enter_Unknown(self):
        self._logger.info(f"Entry action for Unknown state for {self.name}")
        self.check()

    def on_enter_Clearance(self):
        self._logger.info(f"Entry action for Clearance state for {self.name}")
        self.clearance.send(self, message="clearance!")
        self.landingConfirmed() # TODO - for test only
        self.arm_timer(300) # Arm a timer for 5 minutes

    def on_exit_Clearance(self):
        self._logger.info(f"Exit action for Clearance state for {self.name}")
        self.cancel_timer()

    def on_enter_Alert(self):
        self._logger.warning(f"Entry action for Alert state for {self.name}")
        self.alert.send(self, message="alert!")
        self.arm_timer(300) # Arm a timer for 5 minutes

    def on_exit_Alert(self):
        self._logger.warning(f"Exit action for Alert state for {self.name}")
        self.cancel_timer()

    @property
    def is_flying(self):
        # speed > 10km/h ou 2,78m/s
        if self._speed > 2.78:
            return True
        return False

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

        # Adjust the state based on the updated values
        if self._avg_speed > 16.67: # 60km/h or 16,67m/s
            self.highSpeed()
        elif self._avg_speed > 2.78: # 10km/h or 2,78m/s
            self.flying()
        elif (self._avg_speed < 0.56) and (self._altitude_gnd_calc < 60): # 2km/h or 0,56m/s
            self.nullSpeed()

        time_difference = (datetime.now(timezone.utc) - self._last_datetime).total_seconds()
        if time_difference > 300:  # 5 minutes
            self._logger.warning(f"Disconnected for too long. Last seen at {self._last_datetime}.")
            self.disconnected()
        else:
            self.connected()


    def arm_timer(self, duration):
        self.cancel_timer()
        self._timer = threading.Timer(duration, self.timeout)
        self._timer.start()

    def cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
