# Finavia Flights for Home Assistant

Home Assistant integration that turns the departures from Finavia's airports into departure board sensors.

[![GitHub Release][releases-shield]][releases] [![GitHub Release Date][release-date-shield]][releases] [![HACS][hacs-shield]][hacs] [![License][license-shield]](LICENSE)

## What is it?

A custom component that lists the next flights leaving any of Finavia's airports in Finland, from Helsinki-Vantaa to
Ivalo. Each airport is one sensor, with each flight's number, destination, scheduled and estimated time, gate and status.
It's for seeing what is leaving, a departure board on your dashboard, not for keeping track of a flight of your own.

Show the departures with [departures-card](https://github.com/jesmak/departures-card), which draws them as a
departure board, the next flight large with a countdown and the ones after it below. The sensors follow the
[departures format](https://github.com/jesmak/departures-card/blob/main/docs/departures-format.md), the same as the
stops of [Digitransit Live](https://github.com/jesmak/digitransit_live) and the stations of
[Digitraffic Live](https://github.com/jesmak/digitraffic_live), so one card can show an airport next to a bus stop.

The data comes from Finavia's Public Flights API, which needs a free API key of your own.

## Installation

### With HACS

1. Add this repository to HACS custom repositories with type **Integration**
2. Search for Finavia Flights in HACS and download it
3. Restart Home Assistant
4. Get an API key (below), add the integration in Settings › Devices & services, then add airports from its page

### Manual

1. Download the source code from the latest release
2. Copy the `custom_components/finavia_flights` folder to your Home Assistant installation's
   `config/custom_components` folder
3. Restart Home Assistant
4. Get an API key (below), add the integration in Settings › Devices & services, then add airports from its page

### An API key

1. Sign up on [Finavia's API portal](https://apiportal.finavia.fi/)
2. Subscribe to the **Public Flights** API, which is free
3. Copy the key from the portal's **Profile** page

## Settings

### Integration

| Name    | Type     | Description                                                   | Default |
| ------- | -------- | ------------------------------------------------------------- | ------- |
| API key | password | Your key for Finavia's Public Flights API, checked when saved | none    |

The key is asked for once. To change it, choose **Reconfigure** on the integration page. If Finavia stops accepting
it, Home Assistant asks for a new one there.

### Airport

Add with **Add airport** on the integration page. Every airport creates one sensor named after it, in Finnish when Home
Assistant is in Finnish and in English otherwise, such as `sensor.helsinki_vantaa`. Each airport can be added once.

| Name                 | Type   | Description                                 | Default |
| -------------------- | ------ | ------------------------------------------- | ------- |
| Airport              | choice | One of Finavia's 19 airports                | none    |
| Number of departures | number | How many departures the sensor lists, 1–30  | 10      |

Changing an airport changes only the number of departures. To follow another airport, add it and remove the old one.

## Sensors

The state is the time of the next departure that isn't cancelled, Finavia's estimate when it has one and otherwise the
scheduled time. The attributes follow the
[departures format](https://github.com/jesmak/departures-card/blob/main/docs/departures-format.md):

| Attribute            | Description                             |
| -------------------- | --------------------------------------- |
| `departures_version` | Version of the departures format, `1`   |
| `stop_id`            | The airport's IATA code, e.g. `HEL`     |
| `stop_name`          | The airport's name                      |
| `departures`         | The next departures, soonest first      |
| `attribution`        | Data credit                             |

Each departure has:

| Key         | Description                                                                 |
| ----------- | --------------------------------------------------------------------------- |
| `id`        | The scheduled date and flight number, the same on every update              |
| `line`      | Flight number, e.g. `AY9001`                                                |
| `mode`      | Always `plane`                                                              |
| `headsign`  | Destination, with any stops on the way before it, such as `Kittilä, Ivalo`  |
| `scheduled` | Scheduled departure time                                                    |
| `estimated` | Finavia's estimate, or the scheduled time when there is none                |
| `realtime`  | Whether `estimated` is Finavia's estimate                                   |
| `delay`     | Seconds late, negative when early, when there is an estimate               |
| `platform`  | Gate, once one has been given                                               |
| `cancelled` | `true` when the flight is cancelled                                         |
| `notice`    | The flight's status, such as Go to gate, Final call or Gate closed          |

Destinations are in Finnish when Home Assistant is in Finnish and Finavia has a Finnish name, otherwise in English.
Statuses are in Finnish, Swedish or English, following Home Assistant's language, and in English when Finavia has no
text in that language. A cancelled flight has no notice,
because the card says it's cancelled, and neither has a delayed flight whose status only says its time is estimated,
since the card shows the new time and the delay. Keys with no value are left out.

Flights that have left are not listed. Cancelled flights stay in the list until their time has passed. Finavia keeps
them in its data for a day and a half, and a flight more than a minute past its time is left out, as departures-card
would hide it anyway. Only the next departure time is stored in the recorder, not the list.

Departures are fetched every 10 minutes. Finavia's data covers the whole day and a half every time, about 400 KB for
Helsinki-Vantaa, so fetching more often would mostly move the same data again. If a fetch fails the sensor becomes
unavailable until the next one works.

## Examples

### A departure board

```yaml
type: custom:departures-card
entities:
  - sensor.helsinki_vantaa
```

### An airport beside a bus stop

```yaml
type: custom:departures-card
entities:
  - entity: sensor.oulu
  - entity: sensor.lentoasema_0001
    subtitle: Bus to the centre
```

## Data

The flight data comes from [Finavia](https://www.finavia.fi/)'s Public Flights API. Finavia's API portal states no
terms or licence for it, and the sensors credit it as "Finavia".

This is an unofficial integration. It isn't made, endorsed or supported by Finavia, and has no connection to it. Each
user signs up for an API key of their own and uses it under whatever terms Finavia sets, at their own risk. If Finavia
objects to the integration, it will be withdrawn. The icon is Finavia's logo, a trademark of Finavia, and is used only
to show where the data comes from.

### How it is fetched

One request per airport every 10 minutes, to `apigw.finavia.fi/flights/public/v0/flights/dep/<airport>` with the key in
an `app_key` header. The answer is XML with every departure from the previous evening to the next morning. Checking a
key fetches the departures of Enontekiö, one of the smallest airports.

Finavia's status codes differ between airports, so statuses are read by their English text instead. Helsinki-Vantaa
calls a departed flight `DEP` and a cancelled one `CNL`, where the others say `D` and `C`. A flight counts as departed
when its status says so or it has an actual departure time, since a small airport's status can stay empty after
take-off.

## Translating

The integration's UI texts are in `translations/<language>.json`. To add a language, copy `en.json` to the new
language's code and translate the values. Airport names are in `AIRPORTS` in `const.py`, and destinations and statuses
come from Finavia in Finnish, Swedish and English.

## Development

Requires Python 3.14.

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check .
```

| Path                           | What it contains                                        |
| ------------------------------ | ------------------------------------------------------- |
| `__init__.py`                  | Setup: one coordinator per airport                      |
| `config_flow.py`               | The API key, adding an airport and changing it          |
| `api.py`                       | The Public Flights API client                           |
| `flights.py`                   | Finavia's XML → departures in the departures format     |
| `coordinator.py`               | Fetching an airport's departures every 10 minutes       |
| `sensor.py`                    | The departures sensors                                  |
| `const.py`                     | Finavia's airports and the settings                     |
| `translations/<language>.json` | Home Assistant UI texts                                 |

## Support

Hey dude! Help me out for a couple of :beers: or a :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/jesmak)

## License

MIT, see [LICENSE](LICENSE). The Finavia logo in `brand/` is Finavia's trademark and isn't covered by the licence.

[releases-shield]: https://img.shields.io/github/release/jesmak/finavia_flights.svg?style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/jesmak/finavia_flights?style=for-the-badge
[releases]: https://github.com/jesmak/finavia_flights/releases
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs]: https://hacs.xyz/docs/faq/custom_repositories/
[license-shield]: https://img.shields.io/github/license/jesmak/finavia_flights.svg?style=for-the-badge
