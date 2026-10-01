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
    def __init__(self, cfg, fetch_remote_group=False):
        self.logger = get_logger("GuardianAngel")
        self._paragliders = []

        self._event_queue = asyncio.Queue()
        self._stop_monitoring = asyncio.Event()
        self._event_task = None
        self.discord_bot = None
        self._discord_task = None
        self._replay = EventReplay()
        self._confirmation_task = None
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

        # Prefer await sync_group_from_puretrack() (or --sync-group) so network I/O
        # stays off the constructor / event-loop thread.
        self._fetch_remote_group_requested = fetch_remote_group

        for paraglider_cfg in cfg.get('paragliders') or []:
            self.add_paraglider(paraglider_cfg)

    async def sync_group_from_puretrack(self, output_path='cfg/group.json'):
        """Fetch PureTrack group members off the event loop and write group.json."""
        if not self.puretrack_grp:
            self.logger.warning("No PureTrack group configured; skipping remote group sync")
            return None

        grp = await ptrk.get_puretrack_group_async(self.puretrack_grp)
        if not grp or not grp.get('members'):
            self.logger.error("Failed to fetch PureTrack group %s", self.puretrack_grp)
            return None

        config = []
        for paraglider in grp.get('members'):
            config.append({
                "name": paraglider.get('label'),
                "puretrack_key": paraglider.get('key'),
                "discord_id": 0,
                "phone_number": "+33700000000",
                "email": "",
            })

        def _write():
            with open(output_path, 'w', encoding='utf-8') as handle:
                json.dump(config, handle, indent=4)

        await asyncio.to_thread(_write)
        self.logger.info("Synced %s PureTrack members to %s", len(config), output_path)
        return config

    def add_paraglider(self, cfg):
        paraglider = Paraglider(cfg, emit_signals=False, initialize=False)
        self._paragliders.append(paraglider)

        # Connect signals
        paraglider.alert.connect(self.on_alert, weak=False)
        paraglider.clearance.connect(self.on_clearance, weak=False)
        paraglider.initialize()
        session = db.SessionLocal()
        try:
            last_state = db.get_last_paraglider_state(session, paraglider.puretrack_key)
            if last_state is not None:
                paraglider.restore_state(last_state.state)
        finally:
            session.close()
        paraglider.enable_signals()
        paraglider.schedule_pending_timer()

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
        if self._fetch_remote_group_requested:
            await self.sync_group_from_puretrack()
            self._fetch_remote_group_requested = False

        for paraglider in self._paragliders:
            paraglider.schedule_pending_timer()

        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        if self._event_task is None:
            self._event_task = asyncio.create_task(self._process_events())
        if self.discord_bot is None and self.discord_bot_cfg is not None:
            self.logger.info("Starting Discord bot with channel_id=%s", self.discord_bot_cfg.get('channel_id'))
            bot_cfg = dict(self.discord_bot_cfg)
            bot_cfg.setdefault('puretrack_group', self.puretrack_grp)
            self.discord_bot = DiscordBot(bot_cfg)
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
        if self.discord_bot is not None and hasattr(self.discord_bot, 'send_shutdown_message'):
            try:
                await self.discord_bot.send_shutdown_message()
            except Exception as exc:
                self.logger.exception("Failed to send Discord shutdown message: %s", exc)
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
            try:
                event = await asyncio.wait_for(
                    self.discord_bot.pending_confirmation_events.get(),
                    timeout=1,
                )
            except asyncio.TimeoutError:
                continue
            self._apply_confirmation_event(event)

    def _apply_confirmation_event(self, event):
        event_type = event.get('type')
        paraglider_key = event.get('paraglider_key')
        if event_type == 'landing_confirmed':
            self.logger.info("Landing confirmation received from Discord for %s", event.get('discord_id'))
            matched = False
            for paraglider in self._paragliders:
                if paraglider.puretrack_key == paraglider_key:
                    paraglider.landingConfirmed()
                    matched = True
                    break
            if not matched:
                self.logger.warning(
                    "Landing confirmation ignored: unknown PureTrack key %s",
                    paraglider_key,
                )
        elif event_type == 'landing_rejected':
            self.logger.info("Landing confirmation rejected from Discord for %s", event.get('discord_id'))
            matched = False
            for paraglider in self._paragliders:
                if paraglider.puretrack_key == paraglider_key:
                    matched = True
                    # Clearance rejection escalates to Alert; Alert stays active.
                    if paraglider.state == 'Clearance':
                        paraglider.timeout()
                    self._enqueue_event({
                        'type': 'alert',
                        'payload': {
                            'name': paraglider.name,
                            'reason': 'assistance_requested',
                        },
                    })
                    break
            if not matched:
                self.logger.warning(
                    "Landing rejection ignored: unknown PureTrack key %s",
                    paraglider_key,
                )

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
                await asyncio.to_thread(self._replay.record, {'type': event_type, 'payload': payload})
                if self.discord_bot is not None:
                    self.logger.info("Dispatching alert event for %s", payload.get('name'))
                    try:
                        paraglider = self.get_paraglider(payload.get('name'))
                        reason = payload.get('reason')
                        if paraglider is not None:
                            prefix = "🚨 Assistance requested for" if reason == 'assistance_requested' else "⚠️ Alert for"
                            message = (
                                f"{prefix} [{paraglider.name}]"
                                f"(https://puretrack.io/?l=44.91038,5.19237&z=15"
                                f"&group={self.puretrack_grp}&k={paraglider.puretrack_key})"
                            )
                            contacts = []
                            if paraglider.phone_number:
                                contacts.append(f"Phone: {paraglider.phone_number}")
                            if paraglider.email:
                                contacts.append(f"Email: {paraglider.email}")
                            if contacts:
                                message += "\n" + " | ".join(contacts)
                        else:
                            message = f"Alert for {payload.get('name')}"
                        if paraglider is not None and paraglider.discord_id and reason != 'assistance_requested':
                            await self.discord_bot.post_waiting_landing_confirmation(
                                paraglider.discord_id,
                                message,
                                paraglider.puretrack_key,
                                mention_first=False,
                                notification_type='alert',
                            )
                        else:
                            notification_type = (
                                'assistance' if reason == 'assistance_requested' else 'alert'
                            )
                            await self.discord_bot.send_message_async(
                                message,
                                notification_type=notification_type,
                            )
                    except Exception as exc:
                        self.logger.exception("Failed to send alert Discord message: %s", exc)
            elif event_type == 'clearance':
                self.logger.info("Processing clearance event for %s", payload.get('name'))
                await asyncio.to_thread(self._replay.record, {'type': event_type, 'payload': payload})
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
                                notification_type='clearance',
                            )
                        else:
                            await self.discord_bot.send_message_async(
                                message,
                                notification_type='clearance',
                            )
                    except Exception as exc:
                        self.logger.exception("Failed to send clearance Discord message: %s", exc)

            self._event_queue.task_done()

    async def update_states_from_tracking(self, duration):
        responses = {}
        for paraglider in self._paragliders:
            paraglider_key = paraglider.puretrack_key
            tails = await ptrk.get_puretrack_tails_async(paraglider_key, duration + 2)
            if not tails:
                self.logger.warning("No PureTrack data for %s; skipping update", paraglider_key)
                continue
            if self._capture_replay is not None:
                await asyncio.to_thread(
                    self._capture_replay.record,
                    {
                        'type': 'puretrack',
                        'payload': {'key': paraglider_key, 'response': tails},
                    },
                )
            responses[paraglider_key] = tails

        updates = await asyncio.to_thread(self._persist_tracking_responses, responses)
        state_updates = {}
        for paraglider in self._paragliders:
            payload = updates.get(paraglider.puretrack_key)
            if payload is None:
                continue
            paraglider.update(payload)
            state_updates[paraglider.puretrack_key] = paraglider.state
            self.logger.info(
                "Paraglider %s / %s state: %s",
                paraglider.name,
                paraglider.puretrack_key,
                paraglider.state,
            )
            self._queue_state_event_if_changed(paraglider)

        if state_updates:
            await asyncio.to_thread(self._persist_paraglider_states, state_updates)

    def _persist_tracking_responses(self, responses):
        """Parse PureTrack payloads and persist points (runs off the event loop)."""
        session = db.SessionLocal()
        updates = {}
        try:
            for paraglider_key, tails in responses.items():
                self._store_tracking_response(session, paraglider_key, tails)
                last_state = db.get_last_paraglider_state(session, paraglider_key)
                if last_state:
                    updates[paraglider_key] = {
                        'datetime': last_state.datetime.replace(tzinfo=timezone.utc),
                        'coordinates': (last_state.latitude, last_state.longitude),
                        'course': last_state.course,
                        'altitude_gnd_calc': last_state.altitude_gnd_calc,
                        'speed': last_state.speed,
                        'avg_speed': db.calculate_average_speed(session, paraglider_key, minutes=5),
                    }
            db.purge_old_data(session)
        finally:
            session.close()
        return updates

    def _persist_paraglider_states(self, state_by_key):
        session = db.SessionLocal()
        try:
            for paraglider_key, state in state_by_key.items():
                db.update_last_paraglider_state(session, paraglider_key, state)
        finally:
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

        responses = {paraglider.puretrack_key: payload.get('response', {})}
        updates = await asyncio.to_thread(self._persist_tracking_responses, responses)
        update_payload = updates.get(paraglider.puretrack_key)
        if update_payload is not None:
            paraglider.update(update_payload)
            await asyncio.to_thread(
                self._persist_paraglider_states,
                {paraglider.puretrack_key: paraglider.state},
            )
            self.logger.info(
                "Paraglider %s / %s state: %s",
                paraglider.name,
                paraglider.puretrack_key,
                paraglider.state,
            )
            self._queue_state_event_if_changed(paraglider)

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
            db.update_last_paraglider_state(session, paraglider.puretrack_key, paraglider.state)
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

    def _queue_alert_occurrence(self, paraglider):
        self._last_seen_state[paraglider.puretrack_key] = paraglider.state
        self._enqueue_event({'type': 'alert', 'payload': {'name': paraglider.name}})

    def update_state_from_discord(self, name, message):
        paraglider = self.get_paraglider(name)
        if paraglider is not None:
            if message == "landed":
                paraglider.landingConfirmed()

    def _enqueue_event(self, event):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Sync contexts (unit tests): same-thread put_nowait is safe when no loop runs.
            try:
                self._event_queue.put_nowait(event)
            except Exception:
                self.logger.exception("Failed to enqueue event %s", event.get('type'))
            return

        # Already on the event-loop thread: put_nowait is safe and avoids a race
        # with fire-and-forget create_task(put(...)).
        self._event_queue.put_nowait(event)
    def on_alert(self, sender, message):
        self.logger.info(f"Alert signal received from {sender.name}")
        self._queue_alert_occurrence(sender)

    def on_clearance(self, sender, message):
        self.logger.info(f"Clearance signal received from {sender.name} : discord_id {sender.discord_id}")
        self._queue_state_event_if_changed(sender)

    def on_landing_confirmed(self, sender, message):
        self.logger.info(f"Landing confirmed received from {sender.name}")
