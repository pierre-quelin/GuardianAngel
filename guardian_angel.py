import asyncio
import json
from datetime import datetime, timezone

import database as db
import puretrack_api as ptrk
from discord_bot import DiscordBot
from event_replay import EventReplay
from logger import get_logger
from paraglider import Paraglider

class GuardianAngel:
    def __init__(self, cfg):
        self.logger = get_logger("GuardianAngel")
        self._paragliders = []

        # self.discord_bot = DiscordBot(cfg.get('discord_bot'))
        # self.discord_bot.landing_confirmed.connect(self.on_landing_confirmed)
        # self.discord_bot.start_in_thread()

        # self.discord_bot = DiscordApi(cfg.get('discord_bot'))

        self.puretrack_site_cfg = cfg.get('puretrack_site')
        self.puretrack_grp = self.puretrack_site_cfg.get('group')

        db.init_db_engine(cfg.get('database'))

        # Get the list of all paragliders in the group
        config = []
        grp = ptrk.get_puretrack_group(cfg['puretrack_site']['group'])
        for paraglider in grp.get('members'):
            p = {}
            p["name"] = paraglider.get('label')
            p["puretrack_key"] = paraglider.get('key')
            p["discord_id"] = 0
            p["phone_number"] = "+33700000000"
            p["email"] = ""
            config.append(p)
        with open('cfg/group.json', 'w') as f:
            json.dump(config, f, indent=4)

        # grpLive = ptrk.get_puretrack_group_live(cfg['puretrack_site']['group'])
        # for paraglider in grpLive:
        #     elt = ptrk.parse_puretrack_record(paraglider)
        #     self.logger.info(f"{elt.get('key')} : {elt.get('name')} : {elt.get('label')}")
        # ??? strange response

        # Check that all the paragliders in the group are known. If not,...

        # Add all known paragliders
        # TODO - Restore previous states
        for paraglider_cfg in cfg.get('paragliders'):
            self.add_paraglider(paraglider_cfg)

        self._timer = None
        self._monitor_task = None
        self._stop_monitoring = asyncio.Event()
        self._event_queue = asyncio.Queue()
        self._event_task = None
        self.discord_bot = None
        self._discord_task = None
        self._replay = EventReplay()
        self._confirmation_task = None

    def add_paraglider(self, cfg):
        paraglider = Paraglider(cfg)
        self._paragliders.append(paraglider)

        # Connect signals
        paraglider.alert.connect(self.on_alert)
        paraglider.clearance.connect(self.on_clearance)

        self.logger.info(f"Paraglider {paraglider.name} added.")

    def remove_paraglider(self, name):
        if name in self._paragliders:
            # Disconnect signals
            self._paragliders[name].alert.disconnect(self.on_alert)
            self._paragliders[name].clearance.disconnect(self.on_clearance)

            del self._paragliders[name]
            self.logger.info(f"Paraglider {name} removed.")
        else:
            self.logger.info(f"Paraglider {name} does not exist.")

    def get_paraglider(self, name):
        return self._paragliders.get(name, None)

    async def start_monitoring(self, period=30):
        self._stop_monitoring.clear()
        if self._monitor_task is not None:
            self._monitor_task.cancel()
        if self._event_task is None:
            self._event_task = asyncio.create_task(self._process_events())
        if self.discord_bot is None and self.puretrack_site_cfg is not None:
            self.discord_bot = DiscordBot(self.puretrack_site_cfg.get('discord_bot', {}))
            self._discord_task = asyncio.create_task(self.discord_bot.start_async())
            self._confirmation_task = asyncio.create_task(self._handle_confirmation_events())
        self._monitor_task = asyncio.create_task(self._monitor_loop(period))

    async def _monitor_loop(self, period=30):
        while not self._stop_monitoring.is_set():
            try:
                await self.update_states_from_tracking(period)
            except Exception as exc:
                self.logger.exception("Monitoring iteration failed: %s", exc)
            await asyncio.sleep(period)

    async def stop_monitoring(self):
        self._stop_monitoring.set()
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        if self._event_task is not None:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
            self._event_task = None
        if self._confirmation_task is not None:
            self._confirmation_task.cancel()
            try:
                await self._confirmation_task
            except asyncio.CancelledError:
                pass
            self._confirmation_task = None

    async def _handle_confirmation_events(self):
        while not self._stop_monitoring.is_set():
            if self.discord_bot is None:
                await asyncio.sleep(1)
                continue
            event = await self.discord_bot._pending_confirmation_events.get()
            if event.get('type') == 'landing_confirmed':
                self.logger.info("Landing confirmation received from Discord for %s", event.get('discord_id'))
                for paraglider in self._paragliders:
                    if paraglider.discord_id == event.get('discord_id'):
                        paraglider.landingConfirmed()
                        break
            elif event.get('type') == 'landing_rejected':
                self.logger.info("Landing confirmation rejected from Discord for %s", event.get('discord_id'))

    async def _process_events(self):
        while not self._stop_monitoring.is_set():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue

            event_type = event.get('type')
            payload = event.get('payload', {})

            if event_type == 'alert':
                self.logger.info("Processing alert event for %s", payload.get('name'))
                self._replay.record({'type': event_type, 'payload': payload})
                if self.discord_bot is not None:
                    await self.discord_bot.send_message_async(f"Alert for {payload.get('name')}")
            elif event_type == 'clearance':
                self.logger.info("Processing clearance event for %s", payload.get('name'))
                self._replay.record({'type': event_type, 'payload': payload})
                if self.discord_bot is not None:
                    await self.discord_bot.send_message_async(f"Clearance for {payload.get('name')}")

            self._event_queue.task_done()

    async def update_states_from_tracking(self, duration):
        session = db.SessionLocal()

        # Update database
        for paraglider in self._paragliders:
            paraglider_key = paraglider.puretrack_key
            if tails := await ptrk.get_puretrack_tails_async(paraglider_key, duration+2): # +2 to ensure we get the last point
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

            if paraglider.state in {'Alert', 'Clearance'}:
                event_type = 'alert' if paraglider.state == 'Alert' else 'clearance'
                await self._event_queue.put({'type': event_type, 'payload': {'name': paraglider.name}})

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
        asyncio.create_task(self._event_queue.put({'type': 'alert', 'payload': {'name': sender.name}}))
        # TODO - If several alerts are sent, how do you manage the message ids?
        # Sends a message to the guardian angel to check the paraglider
        #  Save the message id to check the response later
        # Waits for the gardian angel's response
        #  If the guardian angel confirms the alert, call paraglider.landingConfirmed()

        # Sends a message to inform the paraglider about the alert

    def on_clearance(self, sender, message):
        self.logger.info(f"Clearance signal received from {sender.name} : discord_id {sender.discord_id}")
        asyncio.create_task(self._event_queue.put({'type': 'clearance', 'payload': {'name': sender.name}}))
        # TODO - Threads
        # Sends a message to the paraglider to confirm the landing
        # asyncio.create_task(self.discord_bot.post_waiting_landing_confirmation(sender.discord_id))
        # Waits for the paraglider's response
        #  If the paraglider confirms the landing, call paraglider.landingConfirmed()
        hour= datetime.now().strftime("%H:%M:%S")
        message = f"[{sender.name}](https://puretrack.io/?l=44.91038,5.19237&z=15&group={self.puretrack_grp}&k={sender.puretrack_key}) - 🕵I've detected your landing at {hour} 🏁. Is everything ok ❓"
        if self.discord_bot is not None:
            asyncio.create_task(self.discord_bot.send_message_async(message))

    def on_landing_confirmed(self, sender, message):
        self.logger.info(f"Landing confirmed received from {sender.name}")
        # TODO - paraglider.landingConfirmed()
