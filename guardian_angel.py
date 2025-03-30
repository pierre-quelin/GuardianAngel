from paraglider import Paraglider
from logger import get_logger
import threading
import puretrack_api as ptrk
import database as db
from datetime import timezone
from discord_bot import DiscordBot

class GuardianAngel:
    def __init__(self, cfg):
        self.logger = get_logger("GuardianAngel")
        self._paragliders = []

        self.discord_bot = DiscordBot(cfg.get('discord_bot'))
        self.discord_bot.landing_confirmed.connect(self.on_landing_confirmed)
        self.discord_bot.start_in_thread()

        database_cfg = cfg.get('database')
        db.init_db_engine(database_cfg.get('url'))

        # Add all known paragliders
        # TODO - Restore previous states
        for paraglider_cfg in cfg.get('paragliders'):
            self.add_paraglider(paraglider_cfg)

        # Get the list of all paragliders in the group
        # grpLive = ptrk.getPureTrackGroupLive(cfg['puretrack']['group'])
        # Check that all the paragliders in the group are known. If not,...

        self._timer = None
        self.start_monitoring()

    def add_paraglider(self, cfg):
        paraglider = Paraglider(cfg)
        self._paragliders.append(paraglider)

        # Connect signals
        paraglider.alert.connect(self.on_alert)
        paraglider.clearance.connect(self.on_clearance)

        paraglider.landingConfirmed() # TODO - For test only

        self.logger.info(f"Paraglider {paraglider.name} added.")

    # def remove_paraglider(self, name):
    #     if name in self._paragliders:
    #         del self._paragliders[name]
    #         self.logger.info(f"Paraglider {name} removed.")
    #     else:
    #         self.logger.info(f"Paraglider {name} does not exist.")

    def get_paraglider(self, name):
        return self._paragliders.get(name, None)

    def start_monitoring(self, period=15):
        self.stop_monitoring()
        self._timer = threading.Timer(period, self._update_states, args=(period,))
        self._timer.start()

    def _update_states(self, duration):
        try:
            self.update_states_from_tracking(duration)
        finally:
            # Restart timer after execution
            self.start_monitoring(duration)

    def stop_monitoring(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def update_states_from_tracking(self, duration):
        session = db.SessionLocal()

        # Update database
        for paraglider in self._paragliders:
            paraglider_key = paraglider.puretrack_key
            if tails := ptrk.get_puretrack_tails(paraglider_key, duration+2): # +2 to ensure we get the last point
                tracks = tails.get('tracks')
                if tracks[0].get('count') != 0:
                    parsed_points = []
                    last_parsed_point = ptrk.parse_puretrack_record(tracks[0].get('last'))
                    points = tracks[0].get('points')
                    # Reversed, the last first
                    for point in reversed(points):
                        parsed_point = ptrk.parse_puretrack_record(point)
                        if parsed_point.get('timestamp') == last_parsed_point.get('timestamp'):
                            # If timestamp is the same, the first record is the only true
                            self.logger.debug("Point: not used. Always registered the first one.")
                            continue
                        if (last_parsed_point.get('speed_calc') == None):
                            last_parsed_point['speed_calc'] = round(ptrk.calculate_speed(parsed_point, last_parsed_point), 2)
                        self.logger.info(f"Point: {last_parsed_point}")
                        parsed_points.append(last_parsed_point)
                        last_parsed_point = parsed_point
                        pass

                    # Add the new points to the database
                    db.update_paraglider_data(session, paraglider_key, parsed_points)

        # Update paragliders states
        # TODO - Check if the paraglider is in the database
        for paraglider in self._paragliders:
            # Update paraglider's speed, coordinates, and course
            # Retrieve the last known state of the paraglider from the database
            last_state = db.get_last_paraglider_state(session, paraglider.puretrack_key)
            if last_state:
                paraglider.update({
                    'datetime': last_state.datetime.replace(tzinfo=timezone.utc), # SQLite doesn't save Time Zone
                    'coordinates': (last_state.latitude, last_state.longitude),
                    'course': last_state.course,
                    'altitude_gnd_calc': last_state.altitude_gnd_calc,
                    # paraglider.speed = last_state.get('speed', last_known_state.get('speed_calc', 0))
                    'speed': last_state.speed,
                    'avg_speed': db.calculate_average_speed(session, paraglider.puretrack_key, minutes=5) # Calculate the average speed over the last 5 minutes
                })
            else:
                pass # TODO - See later if something is needed

            # Log the state of each paraglider
            self.logger.info(f"Paraglider {paraglider.name} / {paraglider.puretrack_key} state: {paraglider.state}")

        # Purge the database of old points
        db.purge_old_data(session)

        session.close()

    def update_state_from_discord(self, name, message):
        paraglider = self.get_paraglider(name)
        if paraglider is not None:
            if message == "landed":
                paraglider.landingConfirmed()

    def on_alert(self, sender, message):
        self.logger.info(f"Alert signal received from {sender.name}")
        # TODO - If several alerts are sent, how do you manage the message ids?
        # Sends a message to the guardian angel to check the paraglider
        #  Save the message id to check the response later
        # Waits for the gardian angel's response
        #  If the guardian angel confirms the alert, call paraglider.landingConfirmed()

        # Sends a message to inform the paraglider about the alert

    def on_clearance(self, sender, message):
        self.logger.info(f"Clearance signal received from {sender.name}")
        # TODO - Threads
        # Sends a message to the paraglider to confirm the landing
        self.discord_bot.post_waiting_landing_confirmation(sender.discord_id)
        # Waits for the paraglider's response
        #  If the paraglider confirms the landing, call paraglider.landingConfirmed()

    def on_landing_confirmed(self, sender, message):
        self.logger.info(f"Landing confirmed received from {sender.name}")
        # TODO - paraglider.landingConfirmed()
