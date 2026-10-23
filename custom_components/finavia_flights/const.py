"""Constants for the Finavia Flights integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "finavia_flights"

# Finavia names no licence for the data, so the credit is just the source.
ATTRIBUTION: Final = "Finavia"

# Version of the departures format the sensors write (docs/departures-format.md in departures-card).
DEPARTURES_VERSION: Final = 1

# {kind} is dep, arr or all, the last both in one answer.
API_URL: Final = "https://apigw.finavia.fi/flights/public/v0/flights/{kind}/{airport}"
API_KEY_HEADER: Final = "app_key"
PORTAL_URL: Final = "https://apiportal.finavia.fi/"
# An airport with few departures, so checking a key doesn't download Helsinki-Vantaa's 400 KB.
KEY_CHECK_AIRPORT: Final = "ENF"

# Every fetch is the airport's whole day and a half, about 400 KB for Helsinki-Vantaa's departures, with no way to ask for less or
# only what changed. Finavia allows every 30 seconds, but nobody follows their own flight with this.
UPDATE_INTERVAL: Final = timedelta(minutes=10)

# Config subentry type and its settings
SUBENTRY_AIRPORT: Final = "airport"
CONF_AIRPORT: Final = "airport"
CONF_DEPARTURES: Final = "departures"
CONF_DIRECTION: Final = "direction"
DIRECTION_DEPARTURES: Final = "departures"
DIRECTION_ARRIVALS: Final = "arrivals"
DIRECTION_BOTH: Final = "both"
DIRECTIONS: Final = [DIRECTION_DEPARTURES, DIRECTION_ARRIVALS, DIRECTION_BOTH]
# The sensors each direction makes, and what Finavia's API calls it.
DIRECTION_SENSORS: Final[dict[str, list[str]]] = {
    DIRECTION_DEPARTURES: [DIRECTION_DEPARTURES],
    DIRECTION_ARRIVALS: [DIRECTION_ARRIVALS],
    DIRECTION_BOTH: [DIRECTION_DEPARTURES, DIRECTION_ARRIVALS],
}
API_KINDS: Final = {DIRECTION_DEPARTURES: "dep", DIRECTION_ARRIVALS: "arr", DIRECTION_BOTH: "all"}
DEFAULT_DEPARTURES: Final = 10
MAX_DEPARTURES: Final = 30

# Finavia's airports by IATA code, with their Finnish and English names.
AIRPORTS: Final[dict[str, tuple[str, str]]] = {
    "ENF": ("Enontekiö", "Enontekiö"),
    "HEL": ("Helsinki-Vantaa", "Helsinki"),
    "IVL": ("Ivalo", "Ivalo"),
    "JOE": ("Joensuu", "Joensuu"),
    "JYV": ("Jyväskylä", "Jyväskylä"),
    "KAJ": ("Kajaani", "Kajaani"),
    "KEM": ("Kemi-Tornio", "Kemi-Tornio"),
    "KTT": ("Kittilä", "Kittilä"),
    "KOK": ("Kokkola-Pietarsaari", "Kokkola-Pietarsaari"),
    "KUO": ("Kuopio", "Kuopio"),
    "KAO": ("Kuusamo", "Kuusamo"),
    "MHQ": ("Maarianhamina", "Mariehamn"),
    "OUL": ("Oulu", "Oulu"),
    "POR": ("Pori", "Pori"),
    "RVN": ("Rovaniemi", "Rovaniemi"),
    "SVL": ("Savonlinna", "Savonlinna"),
    "TMP": ("Tampere-Pirkkala", "Tampere-Pirkkala"),
    "TKU": ("Turku", "Turku"),
    "VAA": ("Vaasa", "Vaasa"),
}


def language_of(hass_language: str) -> str:
    """The language the integration writes in: Finnish, Swedish (statuses only, Finavia has no Swedish place names) or English."""
    language = hass_language.split("-")[0]
    return language if language in ("fi", "sv") else "en"


def airport_name(code: str, language: str) -> str:
    finnish, english = AIRPORTS.get(code, (code, code))
    return finnish if language == "fi" else english
