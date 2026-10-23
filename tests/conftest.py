"""Shared fixtures: departures XML shaped like Finavia's, with made-up flights."""

from __future__ import annotations

from datetime import UTC, datetime
from xml.sax.saxutils import escape

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.finavia_flights.const import API_URL

NOW = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)

# Every field Finavia sends, in its order. Each flight has all of them, empty or not.
FIELDS = (
    "h_apt fltnr sdt sdate acreg actype mfltnr cflight_1 cflight_2 cflight_3 cflight_4 cflight_5 cflight_6 "
    "route_1 route_2 route_3 route_4 route_n_1 route_n_2 route_n_3 route_n_4 route_n_fi_1 route_n_fi_2 route_n_fi_3 "
    "route_n_fi_4 chkarea chkdsk_1 chkdsk_2 calls_1 calls_2 calls_3 calls_4 park park_prv gate gate_prv prm prt prt_f "
    "prt_s est_d pest_d act_d ablk_d callsign"
).split()

# Every field of an arrival, in its order: a departure's without the check-in and gate calls, with the baggage hall.
ARRIVAL_FIELDS = (
    "h_apt fltnr sdt sdate acreg actype mfltnr cflight_1 cflight_2 cflight_3 cflight_4 cflight_5 cflight_6 "
    "route_1 route_2 route_3 route_4 route_n_1 route_n_2 route_n_3 route_n_4 route_n_fi_1 route_n_fi_2 route_n_fi_3 "
    "route_n_fi_4 park park_prv gate gate_prv prm prt prt_f prt_s est_d pest_d act_d ablk_d bltarea callsign"
).split()

# Statuses as Finavia writes them: (English, Finnish, Swedish). The Swedish differs by direction.
STATUSES = {
    "Departed": ("Departed", "Lähtenyt", "Avgått"),
    "Cancelled": ("Cancelled", "Peruttu", "Inställt"),
    "Estimated": ("Estimated", "Arvioitu aika", "Beräknas avgå"),
    "Go to gate": ("Go to gate", "Portille", "Gå till utgång"),
    "Gate closed": ("Gate closed", "Suljettu", "Stängd"),
    "Landed": ("Landed", "Laskeutunut", "Landat"),
    "Approaching": ("Approaching", "Lähestyy", "Landar"),
    "Estimated arrival": ("Estimated", "Arvioitu aika", "Beräknad tid"),
}


def flight(
    number: str,
    scheduled: str,
    *legs: tuple[str, str, str],
    airport: str = "HEL",
    status: str = "",
    code: str = "",
    estimate: str = "",
    gate: str = "",
    actual: str = "",
    hall: str = "",
) -> dict[str, str]:
    """A flight; legs are (IATA code, English name, Finnish name), times ISO 8601 in UTC."""
    values = {"h_apt": airport, "fltnr": number, "sdt": scheduled, "sdate": scheduled[:10].replace("-", ""), "gate": gate}
    values |= {"bltarea": hall}
    for index, (iata, english, finnish) in enumerate(legs, start=1):
        values |= {f"route_{index}": iata, f"route_n_{index}": english, f"route_n_fi_{index}": finnish}
    if status:
        values |= dict(zip(("prt", "prt_f", "prt_s"), STATUSES[status], strict=True)) | {"prm": code}
    if estimate:
        values |= {"est_d": estimate, "pest_d": estimate}
    if actual:
        values |= {"act_d": actual, "ablk_d": actual}
    return values


def block(kind: str, fields: list[str], flights: tuple[dict[str, str], ...]) -> str:
    rows = "".join(
        "<flight>" + "".join(f"<{tag}>{escape(value)}</{tag}>" if (value := f.get(tag)) else f"<{tag}/>" for tag in fields) + "</flight>"
        for f in flights
    )
    description = "Departure flight data" if kind == "dep" else "Arrival flight data"
    return (
        f"<{kind}><header><timestamp>2026-03-14T09:59:00Z</timestamp><from>Finavia</from>"
        f"<description>{description}</description></header><body>{rows}</body></{kind}>"
    )


def board_xml(departures: tuple[dict[str, str], ...] | None = (), arrivals: tuple[dict[str, str], ...] | None = None) -> str:
    """An answer of flights/dep, or of flights/all when there are arrivals; arrivals alone are flights/arr."""
    parts = block("dep", FIELDS, departures) if departures is not None else ""
    if arrivals is not None:
        parts += block("arr", ARRIVAL_FIELDS, arrivals)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<flights xmlns="http://www.finavia.fi/FlightsService.xsd" xmlns:xsd="http://www.w3.org/2001/XMLSchema">{parts}</flights>'
    )


def departures_xml(*flights: dict[str, str]) -> str:
    return board_xml(flights)


def arrivals_xml(*flights: dict[str, str]) -> str:
    return board_xml(None, flights)


# What an unknown airport gets: no dep element at all.
EMPTY_XML = '<?xml version="1.0" encoding="UTF-8"?><flights xmlns="http://www.finavia.fi/FlightsService.xsd"/>'

OULU = ("OUL", "Oulu", "Oulu")
STOCKHOLM = ("ARN", "Stockholm", "Tukholma")
KITTILA = ("KTT", "Kittilä", "Kittilä")
IVALO = ("IVL", "Ivalo", "Ivalo")

HELSINKI_DEPARTURES = (
    flight("AY9001", "2026-03-14T09:30:00Z", OULU, status="Departed", code="DEP", gate="12", actual="2026-03-14T09:41:00Z"),
    flight("AY9003", "2026-03-14T10:20:00Z", STOCKHOLM, status="Cancelled", code="CNL"),
    flight("AY9005", "2026-03-14T10:10:00Z", KITTILA, IVALO, status="Estimated", code="DLU", estimate="2026-03-14T10:40:00Z", gate="31B"),
    flight("AY9007", "2026-03-14T10:30:00Z", OULU, status="Go to gate", code="GTO", gate="14"),
)
HELSINKI_XML = departures_xml(*HELSINKI_DEPARTURES)

# Landed a quarter of an hour ago, landing in 20 minutes, and cancelled.
HELSINKI_ARRIVALS = (
    flight(
        "AY9002",
        "2026-03-14T09:50:00Z",
        OULU,
        status="Landed",
        code="LAN",
        estimate="2026-03-14T09:45:00Z",
        actual="2026-03-14T09:45:00Z",
        hall="2A",
    ),
    flight("AY9004", "2026-03-14T10:20:00Z", STOCKHOLM, status="Estimated arrival", code="EST", estimate="2026-03-14T10:20:00Z", hall="2B"),
    flight("AY9006", "2026-03-14T10:35:00Z", KITTILA, status="Cancelled", code="CNL"),
)
HELSINKI_ALL_XML = board_xml(HELSINKI_DEPARTURES, HELSINKI_ARRIVALS)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Lets Home Assistant load integrations from custom_components/."""


@pytest.fixture
def finavia(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Finavia's API with Helsinki-Vantaa's departures, arrivals and both, and the small airport a key is checked with."""
    aioclient_mock.get(API_URL.format(kind="dep", airport="HEL"), text=HELSINKI_XML)
    aioclient_mock.get(API_URL.format(kind="arr", airport="HEL"), text=arrivals_xml(*HELSINKI_ARRIVALS))
    aioclient_mock.get(API_URL.format(kind="all", airport="HEL"), text=HELSINKI_ALL_XML)
    aioclient_mock.get(API_URL.format(kind="dep", airport="ENF"), text=departures_xml())
    return aioclient_mock
