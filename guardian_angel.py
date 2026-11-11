import asyncio
import json
import os
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
        self._alert_notified = {}
        self._capture_replay = None
        self._state_machine_cfg = cfg.get('state_machine') or {}
        self._avg_speed_window_min = int(self._state_machine_cfg.get('avg_speed_window_min', 5))
        self.puretrack_site_cfg = cfg.get('puretrack_site')
        self.discord_bot_cfg = cfg.get('discord_bot') or (
            self.puretrack_site_cfg.get('discord_bot', {}) if self.puretrack_site_cfg else {}
        )
        self.puretrack_grp = self.puretrack_site_cfg.get('group') if self.puretrack_site_cfg else None
        self.groups = list(cfg.get('groups') or [])
        self.supervisor_channels = list(dict.fromkeys(
            group.get('supervisor_channel_id')
            for group in self.groups
            if group.get('supervisor_channel_id') not in (None, '', 0, '0')
        ))
        if cfg.get('capture_events', False):
            self._capture_replay = EventReplay(cfg.get('capture_file', 'data/puretrack_events.json'))

        db.init_db_engine(cfg.get('database'))

        # Prefer await sync_group_from_puretrack() (or --sync-group) so network I/O
        # stays off the constructor / event-loop thread.
        self._fetch_remote_group_requested = fetch_remote_group

        if self.groups:
            for group in self.groups:
                group_cfg = {
                    'group_name': group.get('name'),
                    'supervisor_channel_id': group.get('supervisor_channel_id'),
                    'supervisor_user_ids': group.get('supervisor_user_ids') or [],
                }
                for paraglider_cfg in group.get('pilots') or []:
                    self.add_paraglider({**group_cfg, **paraglider_cfg})
        else:
            # Support existing flat configs during migration; supervisor IDs may
            # be configured directly on each pilot.
            for paraglider_cfg in cfg.get('paragliders') or []:
                self.add_paraglider(paraglider_cfg)

    async def sync_group_from_puretrack(self, output_path='cfg/group.json', force=False):
        """Create a grouped configuration template from the PureTrack group."""
        if not self.puretrack_grp:
            self.logger.warning("No PureTrack group configured; skipping remote group sync")
            return None

        if not force and os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as handle:
                existing = json.load(handle)
            existing_groups = existing.get('groups') if isinstance(existing, dict) else None
            if isinstance(existing_groups, list) and existing_groups and all(
                isinstance(group, dict)
                and isinstance(group.get('pilots'), list)
                and 0 < len(group['pilots']) <= 8
                for group in existing_groups
            ):
                self.logger.info(
                    "Keeping existing group template at %s; use --sync-group to regenerate it",
                    output_path,
                )
                return existing_groups

        grp = await ptrk.get_puretrack_group_async(self.puretrack_grp)
        if not grp or not grp.get('members'):
            self.logger.error("Failed to fetch PureTrack group %s", self.puretrack_grp)
            return None

        pilots = [
            {
                "name": paraglider.get('label') or f"Pilot {index + 1}",
                "puretrack_key": paraglider.get('key'),
                "discord_user_id": 0,
                "discord_channel_id": 0,
                "phone_number": "",
                "email": "",
            }
            for index, paraglider in enumerate(grp['members'])
        ]
        groups = []
        for index in range(0, len(pilots), 8):
            groups.append({
                "name": f"Ange {index // 8 + 1}",
                "supervisor_channel_id": 0,
                "supervisor_user_ids": [],
                "pilots": pilots[index:index + 8],
            })
        template = {"groups": groups}

        def _write():
            directory = os.path.dirname(output_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as handle:
                json.dump(template, handle, indent=4, ensure_ascii=False)
                handle.write("\n")

        await asyncio.to_thread(_write)
        self.logger.info(
            "Created %s pilot groups (%s pilots) from PureTrack at %s",
            len(groups),
            len(pilots),
            output_path,
        )
        return groups

    def add_paraglider(self, cfg):
        paraglider_cfg = dict(cfg)
        paraglider_cfg['state_machine'] = getattr(self, '_state_machine_cfg', {}) or cfg.get('state_machine')
        paraglider = Paraglider(paraglider_cfg, emit_signals=False, initialize=False)
        self._paragliders.append(paraglider)

        # Connect signals
        paraglider.alert.connect(self.on_alert, weak=False)
        paraglider.clearance.connect(self.on_clearance, weak=False)
        paraglider.takeoff.connect(self.on_takeoff, weak=False)
        paraglider.initialize()
        session = db.SessionLocal()
        try:
            machine_state = db.get_paraglider_machine_state(session, paraglider.puretrack_key)
            if machine_state is not None:
                paraglider.restore_state(machine_state.state)
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
                paraglider.takeoff.disconnect(self.on_takeoff)
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
            supervisor_channels = getattr(self, 'supervisor_channels', [])
            self.logger.info(
                "Starting Discord bot with supervisor channels=%s",
                supervisor_channels,
            )
            bot_cfg = dict(self.discord_bot_cfg)
            bot_cfg.setdefault('puretrack_group', self.puretrack_grp)
            channels = supervisor_channels or [
                bot_cfg.get('discord_channel_id')
            ]
            bot_cfg['supervisor_channels'] = [
                channel_id for channel_id in channels
                if channel_id not in (None, '', 0, '0')
            ]
            bot_cfg['pilot_startup_prompts'] = [
                {
                    'name': paraglider.name,
                    'puretrack_key': paraglider.puretrack_key,
                    'discord_user_id': paraglider.discord_user_id,
                    'discord_channel_id': paraglider.discord_channel_id,
                    'supervisor_channel_id': paraglider.supervisor_channel_id,
                    'supervisor_user_ids': paraglider.supervisor_user_ids,
                }
                for paraglider in self._paragliders
                if (
                    paraglider.discord_channel_id is not None
                    or bot_cfg.get('discord_channel_id') not in (None, '', 0, '0')
                )
            ]
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
            state_updates = self._apply_confirmation_event(event)
            if state_updates:
                persist_source = (
                    'supervisor'
                    if event.get('actor_role') == 'supervisor'
                    else 'discord'
                )
                await asyncio.to_thread(
                    self._persist_paraglider_states,
                    state_updates,
                    persist_source,
                )

    def _apply_confirmation_event(self, event):
        """Apply Discord confirmation on the event loop; return states to persist off-loop."""
        event_type = event.get('type')
        paraglider_key = event.get('paraglider_key')
        state_updates = {}
        if event_type == 'landing_confirmed':
            self.logger.info(
                "Landing confirmation received from Discord for %s (role=%s)",
                event.get('discord_id'),
                event.get('actor_role', 'pilot'),
            )
            matched = False
            for paraglider in self._paragliders:
                if paraglider.puretrack_key == paraglider_key:
                    self._last_seen_state = getattr(self, '_last_seen_state', {})
                    previous_state = paraglider.state
                    self._last_seen_state[paraglider.puretrack_key] = previous_state
                    paraglider.landingConfirmed()
                    state_updates[paraglider.puretrack_key] = paraglider.state
                    self._queue_state_event_if_changed(paraglider)
                    if previous_state == 'Alert' and paraglider.state != 'Alert':
                        self.logger.info(
                            "Alert cleared after positive confirmation for %s",
                            paraglider.name,
                        )
                    matched = True
                    break
            if not matched:
                self.logger.warning(
                    "Landing confirmation ignored: unknown PureTrack key %s",
                    paraglider_key,
                )
        elif event_type == 'landing_rejected':
            self.logger.info(
                "Landing confirmation rejected from Discord for %s (role=%s)",
                event.get('discord_id'),
                event.get('actor_role', 'pilot'),
            )
            matched = False
            for paraglider in self._paragliders:
                if paraglider.puretrack_key == paraglider_key:
                    matched = True
                    # Clearance rejection escalates to Alert; Alert stays active.
                    if paraglider.state == 'Clearance':
                        paraglider.timeout()
                    state_updates[paraglider.puretrack_key] = paraglider.state
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
        elif event_type == 'assistance_requested':
            matched = False
            for paraglider in self._paragliders:
                if paraglider.puretrack_key == paraglider_key:
                    paraglider.request_assistance()
                    state_updates[paraglider.puretrack_key] = paraglider.state
                    matched = True
                    break
            if not matched:
                self.logger.warning(
                    "Assistance request ignored: unknown PureTrack key %s",
                    paraglider_key,
                )
        return state_updates

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
                if not hasattr(self, '_alert_notified'):
                    self._alert_notified = {}
                if self.discord_bot is not None:
                    self.logger.info("Dispatching alert event for %s", payload.get('name'))
                    try:
                        paraglider = self.get_paraglider(payload.get('name'))
                        reason = payload.get('reason')
                        alert_notified = getattr(self, '_alert_notified', {})
                        is_repeat = bool(
                            paraglider is not None
                            and alert_notified.get(paraglider.puretrack_key, False)
                            and reason != 'assistance_requested'
                        )
                        if is_repeat:
                            if paraglider.discord_channel_id is not None:
                                reminder_message = (
                                    f"⚠️ Reminder: alert for [{paraglider.name}]"
                                    f"(https://puretrack.io/?l=44.91038,5.19237&z=15"
                                    f"&k={paraglider.puretrack_key}) is still active.\n"
                                    "Please respond to the alert prompt or ask your angel for help."
                                )
                                await self.discord_bot.send_message_async(
                                    reminder_message,
                                    notification_type='alert',
                                    channel_id=paraglider.discord_channel_id,
                                )
                            continue
                        if paraglider is not None:
                            getattr(self, '_alert_notified', {}).update({
                                paraglider.puretrack_key: True,
                            })
                            prefix = "🚨 Assistance requested for" if reason == 'assistance_requested' else "⚠️ Alert for"
                            message = (
                                f"{prefix} [{paraglider.name}]"
                                f"(https://puretrack.io/?l=44.91038,5.19237&z=15"
                                f"&k={paraglider.puretrack_key})"
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
                        if reason == 'assistance_requested':
                            send_options = {'notification_type': 'assistance'}
                            supervisor_channel_id = (
                                getattr(paraglider, 'supervisor_channel_id', None)
                                if paraglider is not None else None
                            )
                            if supervisor_channel_id is not None:
                                send_options['channel_id'] = supervisor_channel_id
                            await self.discord_bot.send_message_async(message, **send_options)
                        elif paraglider is not None:
                            confirmation_options = {
                                'mention_first': False,
                                'notification_type': 'alert',
                            }
                            pilot_channel_id = getattr(
                                paraglider, 'discord_channel_id', None
                            )
                            if pilot_channel_id is not None:
                                confirmation_options['pilot_channel_id'] = pilot_channel_id
                            supervisor_channel_id = getattr(
                                paraglider, 'supervisor_channel_id', None
                            )
                            supervisor_user_ids = getattr(
                                paraglider, 'supervisor_user_ids', set()
                            )
                            if supervisor_channel_id is not None or supervisor_user_ids:
                                confirmation_options.update({
                                    'supervisor_channel_id': supervisor_channel_id,
                                    'supervisor_user_ids': supervisor_user_ids,
                                    'pilot_name': paraglider.name,
                                })
                            await self.discord_bot.post_waiting_landing_confirmation(
                                paraglider.discord_user_id or None,
                                message,
                                paraglider.puretrack_key,
                                **confirmation_options,
                            )
                        else:
                            await self.discord_bot.send_message_async(
                                message,
                                notification_type='alert',
                            )
                    except Exception as exc:
                        self.logger.exception("Failed to send alert Discord message: %s", exc)
            elif event_type == 'alert_cleared':
                self.logger.info("Processing alert clear event for %s", payload.get('name'))
                if self.discord_bot is not None:
                    try:
                        paraglider = self.get_paraglider(payload.get('name'))
                        if paraglider is not None:
                            getattr(self, '_alert_notified', {}).pop(paraglider.puretrack_key, None)
                            self.discord_bot.clear_pending_alert_confirmations(
                                paraglider.puretrack_key
                            )
                            supervisor_channel_id = (
                                getattr(paraglider, 'supervisor_channel_id', None)
                                or self.discord_bot.discord_channel_id
                            )
                            if supervisor_channel_id is not None:
                                await self.discord_bot.send_message_async(
                                    f"✅ Alert cleared for [{paraglider.name}]"
                                    f"(https://puretrack.io/?l=44.91038,5.19237&z=15"
                                    f"&k={paraglider.puretrack_key}) - the situation is no longer active.",
                                    notification_type='alert_cleared',
                                    channel_id=supervisor_channel_id,
                                )
                    except Exception as exc:
                        self.logger.exception("Failed to send alert clear Discord message: %s", exc)
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
                                f"&k={paraglider.puretrack_key})"
                                f" - 🕵I've detected your landing at {hour} 🏁."
                                " Is everything ok ❓"
                            )
                        else:
                            message = f"Clearance for {payload.get('name')}"
                        if paraglider is not None:
                            confirmation_options = {'notification_type': 'clearance'}
                            pilot_channel_id = getattr(
                                paraglider, 'discord_channel_id', None
                            )
                            if pilot_channel_id is not None:
                                confirmation_options['pilot_channel_id'] = pilot_channel_id
                            supervisor_channel_id = getattr(
                                paraglider, 'supervisor_channel_id', None
                            )
                            supervisor_user_ids = getattr(
                                paraglider, 'supervisor_user_ids', set()
                            )
                            if supervisor_channel_id is not None or supervisor_user_ids:
                                confirmation_options.update({
                                    'supervisor_channel_id': supervisor_channel_id,
                                    'supervisor_user_ids': supervisor_user_ids,
                                    'pilot_name': paraglider.name,
                                })
                            await self.discord_bot.post_waiting_landing_confirmation(
                                paraglider.discord_user_id or None,
                                message,
                                paraglider.puretrack_key,
                                **confirmation_options,
                            )
                        else:
                            await self.discord_bot.send_message_async(
                                message,
                                notification_type='clearance',
                            )
                    except Exception as exc:
                        self.logger.exception("Failed to send clearance Discord message: %s", exc)
            elif event_type == 'takeoff':
                self.logger.info("Processing takeoff event for %s", payload.get('name'))
                await asyncio.to_thread(self._replay.record, {'type': event_type, 'payload': payload})
                if self.discord_bot is not None:
                    self.logger.info("Dispatching takeoff event for %s", payload.get('name'))
                    try:
                        paraglider = self.get_paraglider(payload.get('name'))
                        if paraglider is not None:
                            message = (
                                f"🛫 Take off [{paraglider.name}]"
                                f"(https://puretrack.io/?l=44.91038,5.19237&z=15"
                                f"&k={paraglider.puretrack_key})"
                            )
                        else:
                            message = f"Take off for {payload.get('name')}"
                        send_options = {'notification_type': 'takeoff'}
                        supervisor_channel_id = (
                            getattr(paraglider, 'supervisor_channel_id', None)
                            if paraglider is not None else None
                        )
                        if supervisor_channel_id is not None:
                            send_options['channel_id'] = supervisor_channel_id
                        await self.discord_bot.send_message_async(message, **send_options)
                    except Exception as exc:
                        self.logger.exception("Failed to send takeoff Discord message: %s", exc)

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
                last_point = db.get_last_paraglider_point(session, paraglider_key)
                if last_point:
                    updates[paraglider_key] = {
                        'datetime': last_point.datetime.replace(tzinfo=timezone.utc),
                        'coordinates': (last_point.latitude, last_point.longitude),
                        'course': last_point.course,
                        'altitude_gnd_calc': last_point.altitude_gnd_calc,
                        'speed': last_point.speed,
                        'avg_speed': db.calculate_average_speed(
                            session,
                            paraglider_key,
                            minutes=getattr(self, '_avg_speed_window_min', 5),
                        ),
                    }
            db.purge_old_data(session)
        finally:
            session.close()
        return updates

    def _persist_paraglider_states(self, state_by_key, source='tracking'):
        """Persist machine states (runs off the event loop via asyncio.to_thread)."""
        session = db.SessionLocal()
        try:
            for paraglider_key, state in state_by_key.items():
                db.upsert_paraglider_state(session, paraglider_key, state, source=source)
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
                'tracking',
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
        last_point = db.get_last_paraglider_point(session, paraglider.puretrack_key)
        if last_point:
            paraglider.update({
                'datetime': last_point.datetime.replace(tzinfo=timezone.utc),
                'coordinates': (last_point.latitude, last_point.longitude),
                'course': last_point.course,
                'altitude_gnd_calc': last_point.altitude_gnd_calc,
                'speed': last_point.speed,
                'avg_speed': db.calculate_average_speed(
                    session,
                    paraglider.puretrack_key,
                    minutes=getattr(self, '_avg_speed_window_min', 5),
                ),
            })
            db.upsert_paraglider_state(session, paraglider.puretrack_key, paraglider.state, source='tracking')
        self.logger.info("Paraglider %s / %s state: %s", paraglider.name, paraglider.puretrack_key, paraglider.state)
        self._queue_state_event_if_changed(paraglider)

    def _queue_state_event_if_changed(self, paraglider):
        if not hasattr(self, '_last_seen_state'):
            self._last_seen_state = {}
        state_key = paraglider.state
        previous_state = self._last_seen_state.get(paraglider.puretrack_key)
        if previous_state == state_key:
            return False

        if previous_state == 'Alert' and state_key != 'Alert':
            self._last_seen_state[paraglider.puretrack_key] = state_key
            self._enqueue_event({'type': 'alert_cleared', 'payload': {'name': paraglider.name}})
            return True

        self._last_seen_state[paraglider.puretrack_key] = state_key
        if state_key in {'Alert', 'Clearance'}:
            event_type = 'alert' if state_key == 'Alert' else 'clearance'
            self._enqueue_event({'type': event_type, 'payload': {'name': paraglider.name}})
            return True
        return False

    def _queue_alert_occurrence(self, paraglider, reason=None):
        self._last_seen_state[paraglider.puretrack_key] = paraglider.state
        payload = {'name': paraglider.name}
        if reason is not None:
            payload['reason'] = reason
        self._enqueue_event({'type': 'alert', 'payload': payload})

    def update_state_from_discord(self, name, message):
        paraglider = self.get_paraglider(name)
        if paraglider is not None:
            if message == "landed":
                paraglider.landingConfirmed()

    def _enqueue_event(self, event):
        if not hasattr(self, '_event_queue'):
            return
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
        reason = 'assistance_requested' if message == 'assistance_requested' else None
        self._queue_alert_occurrence(sender, reason=reason)

    def on_clearance(self, sender, message):
        self.logger.info(
            f"Clearance signal received from {sender.name} : discord_user_id {sender.discord_user_id}"
        )
        self._queue_state_event_if_changed(sender)

    def on_takeoff(self, sender, message):
        self.logger.info(f"Takeoff signal received from {sender.name}")
        self._last_seen_state[sender.puretrack_key] = sender.state
        self._enqueue_event({'type': 'takeoff', 'payload': {'name': sender.name}})

    def on_landing_confirmed(self, sender, message):
        self.logger.info(f"Landing confirmed received from {sender.name}")
