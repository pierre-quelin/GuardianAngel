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
    def __init__(self, cfg, fetch_remote_group=True):
        self.logger = get_logger("GuardianAngel")
        self._paragliders = []

        # self.discord_bot = DiscordBot(cfg.get('discord_bot'))
        # self.discord_bot.landing_confirmed.connect(self.on_landing_confirmed)
        # self.discord_bot.start_in_thread()

        # self.discord_bot = DiscordApi(cfg.get('discord_bot'))

        self._event_queue = asyncio.Queue()
        self._stop_monitoring = asyncio.Event()
        self._event_task = None
        self.discord_bot = None
        self._discord_task = None
        self._replay = EventReplay()
        self._confirmation_task = None
        self._timer = None
        self._monitor_task = None
        self._last_seen_state = {}
        self._capture_replay = None
        self.puretrack_site_cfg = cfg.get('puretrack_site')
        self.discord_bot_cfg = cfg.get('discord_bot') or (
            self.puretrack_site_cfg.get('discord_bot', {}) if self.puretrack_site_cfg else {}
        )
        self.puretrack_grp = self.puretrack_site_cfg.get('group') if self.puretrack_site_cfg else None
        if cfg.get('capture_events', False):
            self._capture_replay = EventReplay(cfg.get('capture_file', 'data/puretrack_events.json'))

        db.init_db_engine(cfg.get('database'))

        if fetch_remote_group:
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


    def add_paraglider(self, cfg):
        paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
        self._paragliders.append(paraglider)

        # Connect signals
        paraglider.alert.connect(self.on_alert, weak=False)
        paraglider.clearance.connect(self.on_clearance, weak=False)
        paraglider.initialize()
        paraglider.enable_signals()

        self.logger.info(f"Paraglider {paraglider.name} added.")

    def remove_paraglider(self, name):
        for index, paraglider in enumerate(self._paragliders):
            if paraglider.name == name:
                # Disconnect signals
                paraglider.alert.disconnect(self.on_alert)
                paraglider.clearance.disconnect(self.on_clearance)
                paraglider.cleanup()

                del self._paragliders[index]
                self.logger.info(f"Paraglider {name} removed.")
                return True

        self.logger.info(f"Paraglider {name} does not exist.")
        return False

    def get_paraglider(self, name):
        for paraglider in self._paragliders:
            if paraglider.name == name:
                return paraglider
        return None

    async def cleanup(self):
        await self.stop_monitoring()
        for paraglider in list(self._paragliders):
            self.remove_paraglider(paraglider.name)
        self._last_seen_state.clear()
        if self.discord_bot is not None:
            try:
                await self.discord_bot.close()
            except Exception as exc:
                self.logger.exception("Failed to close Discord bot cleanly: %s", exc)
            self.discord_bot = None

    async def start_monitoring(self, period=30):
        self._stop_monitoring.clear()
        if self._monitor_task is not None:
            self._monitor_task.cancel()
        if self._event_task is None:
            self._event_task = asyncio.create_task(self._process_events())
        if self.discord_bot is None and self.discord_bot_cfg is not None:
            self.logger.info("Starting Discord bot with channel_id=%s", self.discord_bot_cfg.get('channel_id'))
            self.discord_bot = DiscordBot(self.discord_bot_cfg)
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
        for paraglider in getattr(self, '_paragliders', []):
            paraglider.cancel_timer()
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
        if self._discord_task is not None:
            self._discord_task.cancel()
            try:
                await self._discord_task
            except asyncio.CancelledError:
                pass
            self._discord_task = None
        if self.discord_bot is not None and hasattr(self.discord_bot, 'close'):
            try:
                await self.discord_bot.close()
            except Exception as exc:
                self.logger.exception("Failed to close Discord bot: %s", exc)

    async def _handle_confirmation_events(self):
        while not self._stop_monitoring.is_set():
            if self.discord_bot is None:
                await asyncio.sleep(1)
                continue
            event = await self.discord_bot._pending_confirmation_events.get()
            self._apply_confirmation_event(event)

    def _apply_confirmation_event(self, event):
        if event.get('type') == 'landing_confirmed':
            self.logger.info("Landing confirmation received from Discord for %s", event.get('discord_id'))
            for paraglider in self._paragliders:
                if paraglider.puretrack_key == event.get('paraglider_key'):
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
                    self.logger.info("Dispatching alert event for %s", payload.get('name'))
                    try:
                        paraglider = self.get_paraglider(payload.get('name'))
                        if paraglider is not None:
                            message = (
                                f"⚠️ Alert for [{paraglider.name}]"
                                f"(https://puretrack.io/?l=44.91038,5.19237&z=15"
                                f"&group={self.puretrack_grp}&k={paraglider.puretrack_key})"
                            )
                        else:
                            message = f"Alert for {payload.get('name')}"
                        await self.discord_bot.send_message_async(message)
                    except Exception as exc:
                        self.logger.exception("Failed to send alert Discord message: %s", exc)
            elif event_type == 'clearance':
                self.logger.info("Processing clearance event for %s", payload.get('name'))
                self._replay.record({'type': event_type, 'payload': payload})
                if self.discord_bot is not None:
                    self.logger.info("Dispatching clearance event for %s", payload.get('name'))
                    try:
                        paraglider = self.get_paraglider(payload.get('name'))
                        if paraglider is not None:
                            hour = datetime.now().strftime("%H:%M:%S")
                            message = (
                                f"[{paraglider.name}]"
                                f"(https://puretrack.io/?l=44.91038,5.19237&z=15"
                                f"&group={self.puretrack_grp}&k={paraglider.puretrack_key})"
                                f" - 🕵I've detected your landing at {hour} 🏁."
                                " Is everything ok ❓"
                            )
                        else:
                            message = f"Clearance for {payload.get('name')}"
                        if paraglider is not None and paraglider.discord_id:
                            await self.discord_bot.post_waiting_landing_confirmation(
                                paraglider.discord_id,
                                message,
                                paraglider.puretrack_key,
                            )
                        else:
                            await self.discord_bot.send_message_async(message)
                    except Exception as exc:
                        self.logger.exception("Failed to send clearance Discord message: %s", exc)

            self._event_queue.task_done()

    async def update_states_from_tracking(self, duration):
        session = db.SessionLocal()

        # Update database
        for paraglider in self._paragliders:
            paraglider_key = paraglider.puretrack_key
            if tails := await ptrk.get_puretrack_tails_async(paraglider_key, duration+2): # +2 to ensure we get the last point
                if self._capture_replay is not None:
                    self._capture_replay.record({
                        'type': 'puretrack',
                        'payload': {'key': paraglider_key, 'response': tails},
                    })
                self._store_tracking_response(session, paraglider_key, tails)

        # Update paragliders states
        # TODO - Check if the paraglider is in the database
        for paraglider in self._paragliders:
            # Update paraglider's speed, coordinates, and course
            # Retrieve the last known state of the paraglider from the database
            self._update_paraglider_state(session, paraglider)

        # Purge the database of old points
        db.purge_old_data(session)

        session.close()

    async def process_replay_event(self, event):
        """Apply one captured PureTrack or state event through the live pipeline."""
        if event.get('type') != 'puretrack':
            await self._event_queue.put(event)
            return

        payload = event.get('payload', {})
        paraglider = next(
            (item for item in self._paragliders if item.puretrack_key == payload.get('key')),
            None,
        )
        if paraglider is None:
            self.logger.warning("Ignoring replay event for unknown PureTrack key %s", payload.get('key'))
            return

        session = db.SessionLocal()
        self._store_tracking_response(session, paraglider.puretrack_key, payload.get('response', {}))
        self._update_paraglider_state(session, paraglider)
        db.purge_old_data(session)
        session.close()

    def _store_tracking_response(self, session, paraglider_key, tails):
        tracks = tails.get('tracks', [])
        if not tracks or tracks[0].get('count', 0) == 0:
            return

        last = ptrk.parse_puretrack_record(tracks[0].get('last'))
        points = []
        for point in reversed(tracks[0].get('points', [])):
            parsed = ptrk.parse_puretrack_record(point)
            if parsed.get('timestamp') == last.get('timestamp'):
                continue
            if last.get('speed_calc') is None:
                last['speed_calc'] = round(ptrk.calculate_speed(parsed, last), 2)
            points.append(last)
            last = parsed
        db.update_paraglider_data(session, paraglider_key, points)

    def _update_paraglider_state(self, session, paraglider):
        last_state = db.get_last_paraglider_state(session, paraglider.puretrack_key)
        if last_state:
            paraglider.update({
                'datetime': last_state.datetime.replace(tzinfo=timezone.utc),
                'coordinates': (last_state.latitude, last_state.longitude),
                'course': last_state.course,
                'altitude_gnd_calc': last_state.altitude_gnd_calc,
                'speed': last_state.speed,
                'avg_speed': db.calculate_average_speed(session, paraglider.puretrack_key, minutes=5),
            })
        self.logger.info("Paraglider %s / %s state: %s", paraglider.name, paraglider.puretrack_key, paraglider.state)
        self._queue_state_event_if_changed(paraglider)

    def _queue_state_event_if_changed(self, paraglider):
        state_key = paraglider.state
        previous_state = self._last_seen_state.get(paraglider.puretrack_key)
        if previous_state == state_key:
            return False

        self._last_seen_state[paraglider.puretrack_key] = state_key
        if state_key in {'Alert', 'Clearance'}:
            event_type = 'alert' if state_key == 'Alert' else 'clearance'
            self._enqueue_event({'type': event_type, 'payload': {'name': paraglider.name}})
            return True
        return False

    def update_state_from_discord(self, name, message):
        paraglider = self.get_paraglider(name)
        if paraglider is not None:
            if message == "landed":
                paraglider.landingConfirmed()

    def _enqueue_event(self, event):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            try:
                loop.create_task(self._event_queue.put(event))
            except RuntimeError:
                self._event_queue.put_nowait(event)
        else:
            try:
                self._event_queue.put_nowait(event)
            except RuntimeError:
                pass

    def on_alert(self, sender, message):
        self.logger.info(f"Alert signal received from {sender.name}")
        self._queue_state_event_if_changed(sender)
        # TODO - If several alerts are sent, how do you manage the message ids?
        # Sends a message to the guardian angel to check the paraglider
        #  Save the message id to check the response later
        # Waits for the gardian angel's response
        #  If the guardian angel confirms the alert, call paraglider.landingConfirmed()

        # Sends a message to inform the paraglider about the alert

    def on_clearance(self, sender, message):
        self.logger.info(f"Clearance signal received from {sender.name} : discord_id {sender.discord_id}")
        self._queue_state_event_if_changed(sender)

    def on_landing_confirmed(self, sender, message):
        self.logger.info(f"Landing confirmed received from {sender.name}")
        # TODO - paraglider.landingConfirmed()
