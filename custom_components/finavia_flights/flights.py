"""An airport's departures from Finavia's XML, in the departures format.

Statuses are read by their English text, not their code: the codes differ between airports (Helsinki-Vantaa's DEP,
CNL and GTO are D, C and GO elsewhere) while the texts are the same everywhere.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .api import FinaviaError

NS = "{http://www.finavia.fi/FlightsService.xsd}"
DEPARTED = "Departed"
CANCELLED = "Cancelled"
# Statuses the card already shows on its own, so they make no notice: it says "cancelled" itself, and a new time with
# its delay is what "Estimated" means.
NO_NOTICE = frozenset({CANCELLED, "Estimated"})
# Up to four legs per flight, the destination and the stops on the way.
LEGS = range(1, 5)
# The status text's field by language; English is prt.
STATUS_FIELDS = {"fi": "prt_f", "sv": "prt_s"}
# departures-card hides a departure more than a minute past its estimated time. Finavia keeps cancelled flights, and
# the odd one that never left, for its whole day and a half, so they would take the list's first places for hours.
PAST = timedelta(minutes=1)


@dataclass(frozen=True)
class Departure:
    id: str
    line: str
    headsign: str | None
    scheduled: datetime
    # The public estimate when there is one, otherwise the scheduled time.
    estimated: datetime
    realtime: bool
    gate: str | None
    cancelled: bool
    notice: str | None

    def as_attribute(self) -> dict[str, Any]:
        """The departure in the departures format; fields with no value are left out."""
        attribute = {
            "id": self.id,
            "line": self.line,
            "mode": "plane",
            "headsign": self.headsign,
            "scheduled": self.scheduled.isoformat(),
            "estimated": self.estimated.isoformat(),
            "realtime": self.realtime,
            "delay": int((self.estimated - self.scheduled).total_seconds()) if self.realtime else None,
            "platform": self.gate,
            "cancelled": self.cancelled or None,
            "notice": self.notice,
        }
        return {key: value for key, value in attribute.items() if value is not None}


def parse_departures(xml: bytes | str, language: str, count: int, now: datetime) -> list[Departure]:
    """The airport's next departures in order of their estimated time, without the flights that have left or are past.

    An unknown airport and one with no flights both come as an empty list.
    """
    try:
        root = ET.fromstring(xml)
    # An encoding in the XML declaration that Python doesn't know or ElementTree can't read is a LookupError or ValueError.
    except (ET.ParseError, LookupError, ValueError) as err:
        raise FinaviaError(f"Finavia's answer isn't XML: {err}") from err
    if root.tag != f"{NS}flights":
        raise FinaviaError(f"Finavia's answer isn't a list of flights but {root.tag}")
    departures = [
        departure
        for flight in root.iterfind(f"{NS}dep/{NS}body/{NS}flight")
        if (departure := parse_flight(flight, language)) and departure.estimated >= now - PAST
    ]
    departures.sort(key=lambda departure: departure.estimated)
    return departures[:count]


def parse_flight(flight: ET.Element, language: str) -> Departure | None:
    """One departure, or None for a flight that has left, which can't be boarded, or one without a number or time.

    A flight has left when its status says so or it has an actual departure time: at the smaller airports the status
    sometimes stays empty after take-off.
    """

    def text(tag: str) -> str:
        return (flight.findtext(NS + tag) or "").strip()

    line, scheduled = text("fltnr"), parse_time(text("sdt"))
    status = text("prt")
    if not line or scheduled is None or status == DEPARTED or text("act_d"):
        return None
    estimate = parse_time(text("pest_d"))
    cancelled = status == CANCELLED
    return Departure(
        id=f"flight:{scheduled.date().isoformat()}/{line}",
        line=line,
        headsign=", ".join(name for leg in LEGS if (name := leg_name(text, leg, language))) or None,
        scheduled=scheduled,
        estimated=estimate or scheduled,
        realtime=estimate is not None,
        gate=text("gate") or None,
        cancelled=cancelled,
        # English when Finavia has no text in the language, as it sometimes has no Finnish place name.
        notice=None if status in NO_NOTICE else (text(STATUS_FIELDS.get(language, "prt")) or status or None),
    )


def leg_name(text: Callable[[str], str], leg: int, language: str) -> str:
    """A leg's place in Finnish when asked and Finavia has it, otherwise in English, or its IATA code as a last resort."""
    finnish = text(f"route_n_fi_{leg}") if language == "fi" else ""
    return finnish or text(f"route_n_{leg}") or text(f"route_{leg}")


def parse_time(value: str) -> datetime | None:
    """Finavia's times are ISO 8601 in UTC, "2026-10-23T06:30:00Z"."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None
