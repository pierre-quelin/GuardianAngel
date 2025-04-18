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

cf. [discord.py](https://discordpy.readthedocs.io)

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

[*] --> Root

state Root {

    [*] --> Unknown

    note right of Unknown : Requires checking
    state Unknown {
        Unknown : entry()
    }

    state Flying {
    }

    note right of Clearance : Sends a message to the paraglider\nArm a timer
    state Clearance {
        Clearance : entry()
    }

    state Landed {
    }

    state Disconnected {
    }

    note right of Alert : Sends a message to the guardian angel\nSends a message to inform the paraglider\nArm a timer
    state Alert {
        Alert : entry()
    }

    Alert -> Landed : landingConfirmed()
    Alert -> Alert : timeout()
    Clearance -> Landed : landingConfirmed()
    Clearance -> Alert : timeout()
    Disconnected --> Unknown : connected()
    Disconnected --> Alert : timeout()
    Flying --> Clearance : nullSpeed()
    Flying --> Alert : highSpeed()
    Flying --> Disconnected : disconnected()
    Landed --> Flying : flying()
    Unknown --> Flying : [isFlying()]
    Unknown --> Clearance : [!isFlying()]
}

@enduml
```

# Run inside a Docker container

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
docker run --rm -it --restart=always \
    -v $(pwd)/config.json:/usr/src/app/config.json \
    -v $(pwd)/log:/usr/src/app/log \
    -v $(pwd)/data:/usr/src/app/data \
    guardian-angel

```

Running the container with volumes (for development) :
``` sh
docker run --rm -it --restart=always \
    -v $(pwd):/usr/src/app \
    guardian-angel
```