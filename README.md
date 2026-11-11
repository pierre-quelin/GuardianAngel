# GuardianAngel

Paragliders' virtual guardian angel

The famous international friendly paragliding competition "Hike & Fly" organized by the Tichodromes in the Vercors “La batouchoncel” still had no virtual guardian angel

History
* [Batouchoncel 2021](https://www.youtube.com/watch?v=ISOV66rYnEU)
* [Batouchoncel 2022](https://www.youtube.com/watch?v=za7qylVp3tc)
* [Batouchoncel 2023](https://www.youtube.com/watch?v=Jt0_ezJef30)
* [Batouchoncel 2024](https://www.youtube.com/watch?v=PpSno4xAyYw)

# Goal

Usually, to ensure the safety of the event, 5 "Guardian Angels" follow 40 "Adventurers" in real time on the live tracking [PureTrack](https://puretrack.io) site for 21h.

Every 1/4 hour, each Guardian Angel checks on the progress of each of the 8 Adventurers he is to follow. This runs for the whole 21 hours of the event.

In the event of a suspected accident, the Guardian Angels inform the organization, which then “clears up any doubts” and, if necessary, calls for help, giving information on the last known position, direction, the color of the Adventurer's sail, etc.

The idea of the virtual Guardian Angel would be to automatically monitor the Adventurers and to automatically send an alarm message to each Guardian Angel in case of doubt.

Use-case
* The guardian angel receives a discord message, e-mail, SMS, etc. from the virtual guardian angel. It says “Patrick Dupont is on a suspicious break” with an html link to his PureTrack recording.
* The guardian angel clicks on the link. In his web browser on the PureTrack page, locates Patrick Dupont, looks at his track to see if it confirms the suspicions. Possibly calls Patrick to ask how he's doing.
* If Patrick doesn't answer, the guardian angel calls for help.

# Requirements

## Current reimplementation

The current implementation is coroutine-compatible and uses `asyncio` to
coordinate PureTrack monitoring, event processing, and Discord communication.

It supports:

* asynchronous monitoring without blocking the Discord client;
* Discord notifications routed by pilot group;
* startup and shutdown notifications in each group's supervisor channel;
* a startup message in each pilot channel explaining how to report a problem at any time with `👎`;
* targeted Discord alert confirmations that remain valid until the alert is
    acknowledged or cleared;
* optional delivery of the same landing-confirmation message by Discord DM;
* landing confirmation replies from the targeted pilot or a supervisor
    configured for that pilot's group;
* confirmation by text reply (`yes`, `I am safe`, `I am safe and have landed`) or by `👍` / `👌` reaction;
* negative response by text reply (`no`, `I need assistance`, `I am not safe`) or by `👎` reaction;
* multiple paragliders sharing the same Discord user ID, with each confirmation
    associated with the PureTrack key of the message being answered;
* optional capture of raw PureTrack responses for offline testing;
* replay of captured events without contacting PureTrack, with an optional
    dry-run mode that disables Discord notifications.

Each group has a supervisor channel and its own list of supervisors; with a
flat/minimal configuration, `supervisor_user_ids` can instead be set directly
on the pilot. Each pilot can have a channel for landing confirmations and
related conversations; if omitted, the bot's global Discord channel is used.
Alerts go to the pilot's group's supervisor channel. To also send a copy of a
confirmation to the pilot by direct message, set `send_confirmation_dm` to
`true`; DMs remain optional and replies to them are accepted.

## Running locally (without Docker)

Run these commands from the repository root. Python 3.11 or newer is
recommended:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
mkdir -p logs data
```

Create a local runtime configuration from the example if you do not already
have one:

```sh
cp cfg/config.base.json cfg/config.json
```

Edit `cfg/config.json` and replace the example values. Create a Discord
category for each group, then create its supervisor channel (for example
`👼-angel`) and one channel per pilot. The category name is the group's `name`
(for example `Ange Clint E.`); `Batouchoncel` remains the event name and does
not need a configuration field. Configure the group's supervisor channel ID
and supervisor user IDs, and each pilot's PureTrack key, Discord user ID, and
channel ID. Set the bot token in the environment rather than committing it to
the configuration:

```sh
export DISCORD_BOT_TOKEN="<your Discord bot token>"
```

Start the application from the repository root:

```sh
python main.py
```

On first startup, the application extracts the configured PureTrack group and
creates `cfg/group.json` as a setup template, split into groups of at most eight
pilots. Review the generated pilot groups, configure their supervisor and
channel IDs, and copy the groups into `guardian_angel.groups` in
`cfg/config.json`. Existing grouped templates are preserved on later starts;
use `--sync-group` to regenerate the template explicitly (this replaces manual
edits in `cfg/group.json`). The application then begins monitoring from
`cfg/config.json`. Logs are written to
`logs/application.log`; the SQLite database is stored under `data/`. To stop
the application, press `Ctrl+C`.

Run the automated tests with:

```sh
.venv/bin/pytest -q
```

Replay a captured event file without network notifications:

```sh
python main.py --replay --dry-run \
        --replay-file data/puretrack_events.json \
        --delay 0
```

Raw PureTrack capture is disabled by default. Enable it in the runtime
configuration with `capture_events` and choose the output path with
`capture_file`. Keep runtime configuration files containing bot tokens,
Discord IDs, or channel IDs outside version control.

## Retrieving information from PureTrack

Recover from PureTrack, automatically, every minute, for all the Adventurers in the group

Last known position(s)
* timestamp
* coordinate : lat, long
* speed
* v_speed

# Processing the data received

Detect
* flying
* walking
* hitchhiking
* normal break
* **suspicious break**

# Sending an alert

## email (google,..)

500 emails per day

## Mail Twilio SendGrid

15€ per month for 50,000 emails

## Discord

Implemented with [discord.py](https://discordpy.readthedocs.io) (`discord.ext.commands.Bot`, prefix `>`).

**Configuration** (`guardian_angel` in the runtime JSON):

* `discord_bot.bot_token` — used if `DISCORD_BOT_TOKEN` is not set (prefer the env var).
* `groups[]` — Discord supervision group, named after its category.
* `groups[].supervisor_channel_id` — the group's supervisor channel. Startup,
  shutdown, takeoff, assistance, and alert notifications are sent here.
* `groups[].supervisor_user_ids` — Discord user IDs allowed to acknowledge
  confirmation requests for pilots in that group.
* `groups[].pilots[]` — pilots belonging to this group.
* `groups[].pilots[].discord_channel_id` — channel for that pilot's landing
  confirmation and related conversation.
* `discord_bot.send_confirmation_dm` — if `true`, confirmation requests are
  also copied to the pilot's `discord_user_id` by DM. DMs remain optional in
  addition to group and pilot channels.
* Optional: `discord_bot.send_max_retries` (default 3) and `send_base_backoff` (seconds) for HTTP 429 retries.

Intents: default + `message_content` + `reactions`.

**Outbound embeds** (title / colour):

| Type | When |
|---|---|
| `GUARDIAN ANGEL ONLINE` | monitoring start |
| `GUARDIAN ANGEL OFFLINE` | monitoring stop |
| `TAKE OFF` | entry into state `Flying` (live transition only; not after restore) |
| `LANDING CHECK` | state `Clearance` — asks the pilot if the landing is OK |
| `ALERT - NO RESPONSE` | state `Alert` — initial supervisor alert and reminder prompt |
| `ALERT CLEARED` | the alert is no longer active; supervisors are notified once it ends |
| `ALERT ACKNOWLEDGED` | an alert confirmation was acknowledged by the pilot or a group supervisor |
| `ASSISTANCE REQUESTED` | pilot replied negatively (`👎` / “I need assistance”) |

Alert and clearance messages include the pilot name, a PureTrack link (`…&k=<puretrack_key>`), and phone/email when present. The initial Alert creates a single supervisor notification; reminder cycles keep only the pilot informed until the alert is acknowledged or cleared. A configured group supervisor can acknowledge even when the pilot has no `discord_user_id`. If the pilot has a `discord_user_id`, they are **mentioned** (and optionally DM’d).

**Inbound confirmation** (tied to the PureTrack key of the message, so several pilots can share one Discord user):

* Who may reply: the targeted pilot **or** a supervisor ID listed for the pilot's group. Supervisors can only acknowledge requests for their own group. Others get “not addressed”.
* Reply on the pilot channel message or on the optional DM: positive (`yes`, `I am safe`, `I am safe and have landed`) → `landingConfirmed()` → `Landed`; negative (`no`, `I need assistance`, `I am not safe`) → Clearance escalates to `Alert`, supervisors get `ASSISTANCE REQUESTED`.
* After a negative response, the follow-up message explains the next actions. Reacting with `👍` confirms the pilot is safe and landed, cancelling the assistance request and clearing the alert; `👎` confirms assistance is still needed.
* Reactions: `👍` / `👌` positive, `👎` negative (skin-tone variants accepted). A pilot can also react with `👎` to the startup message at any time to report a problem; the bot raises an alert and sends a follow-up that can be answered with `👍` to cancel the assistance request. Handled via `on_raw_reaction_add` so it works if the message is not in cache.
* Audit: Discord events carry `actor_role` (`pilot` | `supervisor`); persisted machine-state `source` is `supervisor` when a supervisor acknowledges.
* Pending confirmations expire after 300 s. Unrecognised replies get a short hint; the original message stays open.

**Commands** (prefix `>`): `echo`, `check @member` (placeholder “is flying” + PureTrack group link).

Email, Signal, and SMS below are **not** implemented; Discord is the only live notification channel.


## Signal

cf. [signal-cli](https://github.com/AsamK/signal-cli)

## SMS

Requires paid account

e.g. [Twilio](https://www.twilio.com/)
twilio pip module
Rate 0.01€ to 0.05€ per SMS

Others: Nexmo (Vonage), Plivo, Sinch

# Warning criteria

Zero speed for x minutes.

Ground height.

Loss of signal.

No more PureTrack reports.
...

“If in the last 5 minutes, the position has not changed by more than 100m (excluding “absurd” points), then the guy is on pause.”

“If before the pause (so between h-10 minutes and h-5 minutes) his speed exceeded 10km/h several times (excluding absurd speeds >100km/h), he was flying ... so he's just landed or crashed = suspicious break.”

# Interface

## Status summary table

Display the list of paragliders via a small web interface, highlighting those in difficulty and possibly adding a color code (green: ok red: nok).

# The state machine

To view the diagram, copy the code below into the online tool [PlantUML Online](http://www.plantuml.com/plantuml/).
```plantuml
@startuml

[*] --> Root : cold start / init()
[*] --> hist : restore_state(persisted)

note right of Root : At startup, restore the last persisted state when available

state Root {
    state "H*" as hist <<deepHistory>>

    [*] --> Initial
    Initial --> Unknown : init()

    state Unknown {
        Unknown : entry / arm_timer(unknown_timeout_s)
        Unknown : entry / tick() if last_datetime != null
        Unknown : exit / cancel_timer()
    }

    state Flying {
        Flying : entry / signal takeoff (if signals enabled)
    }

    note right of Clearance
      entry / signal clearance + arm_timer(clearance_timeout_s)
      exit / cancel_timer()
    end note
    state Clearance {
        Clearance : entry()
    }

    state Landed {
    }

    note right of Disconnected
      entry / arm_timer(disconnected_timeout_s)
      exit / cancel_timer()
      Loss of recent track = safety path
    end note
    state Disconnected {
        Disconnected : entry()
    }

    note right of Alert
      entry / signal alert + arm_timer(alert_repeat_timeout_s)
      exit / cancel_timer()
      timeout() re-enters Alert (re-notify)
    end note
    state Alert {
        Alert : entry()
    }

    Alert --> Landed : landingConfirmed()
    Alert --> Alert : timeout()
    Clearance --> Landed : landingConfirmed()
    Clearance --> Alert : timeout()
    Disconnected --> Alert : timeout()
    Unknown --> Alert : timeout()

    Flying --> Clearance : tick()\n[has_recent_data && is_stopped && is_near_ground]
    Flying --> Clearance : tick()\n[has_recent_data && is_avg_stopped && is_near_ground]
    Flying --> Alert : tick()\n[has_recent_data && is_high_speed]
    Flying --> Disconnected : tick()\n[is_disconnected]
    Landed --> Flying : tick()\n[is_flying]
    Landed --> Disconnected : tick()\n[is_disconnected]
    Unknown --> Flying : tick()\n[is_flying]
    Unknown --> Disconnected : tick()\n[is_disconnected]
    Unknown --> Landed : tick()\n[has_recent_data && !is_flying]
    Disconnected --> Unknown : tick()\n[has_recent_data]
}

note bottom of Root
  tick() is evaluated in add_transition order (first match wins).
  H* re-runs the restored substate entry (timers; signals if enabled).
  Telemetry is outside the machine; update() writes sensors then tick().

  Predicates (cfg/state_machine):
  - has_recent_data: 0 <= age(last_datetime) <= max_track_age_s
  - is_disconnected: last_datetime != null && !has_recent_data
  - is_flying: has_recent_data && avg_speed > flying_speed_mps
  - is_stopped: speed < stopped_speed_mps
  - is_avg_stopped: avg_speed < stopped_speed_mps
  - is_near_ground: altitude_gnd_calc < clearance_max_agl_m
  - is_high_speed: avg_speed > high_speed_mps
  avg_speed = weighted mean over avg_speed_window_min (DB)

  Grey zone: stay Flying when no tick() guard matches
  (fresh data, not stopped+ground, not high_speed).
end note

@enduml
```

# Running inside a Docker container

Building the image :
``` sh
docker build -t guardian-angel .
```

Export the Docker image :
``` sh
docker save -o guardian-angel.tar guardian-angel
```

Running the container with specific config.json :
``` sh
docker run -it --restart=unless-stopped \
    -e DISCORD_BOT_TOKEN \
    -v $(pwd)/cfg/config.json:/usr/src/app/cfg/config.json \
    -v $(pwd)/logs:/usr/src/app/logs \
    -v $(pwd)/data:/usr/src/app/data \
    guardian-angel

```

Running the container with volumes (for development) :
``` sh
docker run -it --restart=unless-stopped \
    -e DISCORD_BOT_TOKEN \
    -v $(pwd):/usr/src/app \
    guardian-angel
```
