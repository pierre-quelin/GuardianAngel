from paraglider import Paraglider
from logger import get_logger
import threading
import puretrack_api as ptrk

class GuardianAngel:
    def __init__(self, cfg):
        self.logger = get_logger("GuardianAngel")
        self._paragliders = []
        for paraglider_cfg in cfg['paragliders']:
            self.add_paraglider(paraglider_cfg)

        self._timer = None
        self.start_monitoring()

    def add_paraglider(self, cfg):
        paraglider = Paraglider(cfg)
        self._paragliders.append(paraglider)

        # Connect signals
        paraglider.alert.connect(self.on_alert)
        paraglider.clearance.connect(self.on_clearance)
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
            # Redémarrer le timer après l'exécution
            self.start_monitoring(duration)

    def stop_monitoring(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def update_states_from_tracking(self, duration):
        for paraglider in self._paragliders:
            paraglider_key = paraglider.puretrack_key
            if tails := ptrk.get_puretrack_tails(paraglider_key, duration+2): # +2 to ensure we get the last point
                tracks = tails.get('tracks')
                if tracks[0].get('count') != 0:
                    parsed_points = []
                    last_parsed_point = ptrk.parse_puretrack_record(tracks[0].get('last'))
                    points = tracks[0].get('points')
                    # Revesed, the last first
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

                    # # Add the new points to the database
                    # db.update_paraglider_data(session, paraglider_key, parsed_points)

                    # # Calculate the average speed over the last 5 minutes
                    # avg_speed = db.calculate_average_speed(session, paraglider_key, minutes=5)
                    # avg_speed2 = db.calculate_average_speed2(session, paraglider_key, minutes=5)
                    # self.logger.info(f"Average speed for {paraglider_key} over the last 5 minutes: {avg_speed*3.6} {avg_speed2*3.6} km/h")


        # Simulate getting speeds from a tracking site
        # for paraglider in self._paragliders:
        #     speed = self.get_speed_from_tracking(paraglider.puretrack_key)
        #     paraglider.speed = speed

            # last_datetime = paraglider.last_datetime
            # if last_datetime > 5 minutes ago:
            #     paraglider.disconnected()
            #     paraglider.connected()

    def update_state_from_discord(self, name, message):
        paraglider = self.get_paraglider(name)
        if paraglider is not None:
            if message == "landed":
                paraglider.landingConfirmed()


    def get_speed_from_tracking(self, paraglider):
        # Simulate getting speed from a tracking site
        return random

    def on_alert(self, sender, message):
        self.logger.info(f"Alert signal received: from {message}")
        # TODO - If several alerts are sent, how do you manage the message ids?
        # Sends a message to the guardian angel to check the paraglider
        #  Save the message id to check the response later
        # Waits for the gardian angel's response
        #  If the guardian angel confirms the alert, call paraglider.landingConfirmed()

        # Sends a message to inform the paraglider about the alert

    def on_clearance(self, sender, message):
        self.logger.info(f"Clearance signal received: from {message}")
        # TODO
        # Sends a message to the paraglider to confirm the landing
        #  Save the message id to check the response later
        # Waits for the paraglider's response
        #  If the paraglider confirms the landing, call paraglider.landingConfirmed()
