"""An airport's departures and arrivals from Finavia's XML, in the departures format.

Statuses are read by their English text, not their code: the codes differ between airports and directions (Helsinki-
Vantaa's DEP, CNL and DLU are D, C and E elsewhere, and an estimated arrival is EST there) while the texts are the same
everywhere.
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
LANDED = "Landed"
CANCELLED = "Cancelled"
# Statuses the card already shows on its own, so they make no notice: it says "cancelled" and "landed" itself, and a
# new time with its delay is what "Estimated" means.
NO_NOTICE = frozenset({CANCELLED, LANDED, "Estimated"})
# Up to four legs per flight: a departure's destination and the stops on the way, an arrival's origin and its stops.
LEGS = range(1, 5)
# The status text's field by language; English is prt.
STATUS_FIELDS = {"fi": "prt_f", "sv": "prt_s"}
# departures-card hides a departure more than a minute past its estimated time. Finavia keeps cancelled flights, and
# the odd one that never left, for its whole day and a half, so they would take the list's first places for hours.
DEPARTURE_PAST = timedelta(minutes=1)
# A landed flight's time is its landing time when Finavia gives one, so the minute would hide it the moment it lands.
# Half an hour covers the bags, and the card keeps it as long.
ARRIVAL_PAST = timedelta(minutes=30)
# Of the arrivals that are over (see is_over), only the latest two are listed besides the count, as departures-card does.
LANDED_LISTED = 2


@dataclass(frozen=True)
class Departure:
    """A departure, or an arrival in an arrivals sensor: the departures format has one shape for both."""

    id: str
    line: str
    # Where a departure goes, or where an arrival comes from.
    headsign: str | None
    scheduled: datetime
    # Finavia's time when it has one, an arrival's landing time first, otherwise the scheduled time.
    estimated: datetime
    realtime: bool
    # A departure's gate, or an arrival's baggage hall.
    platform: str | None
    cancelled: bool
    notice: str | None
    arrived: bool = False

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
            "platform": self.platform,
            "cancelled": self.cancelled or None,
            "arrived": self.arrived or None,
            "notice": self.notice,
        }
        return {key: value for key, value in attribute.items() if value is not None}


def parse_board(xml: bytes | str) -> ET.Element:
    """Finavia's answer as XML, checked to be its list of flights. An unknown airport is one with no flights."""
    try:
        root = ET.fromstring(xml)
    # An encoding in the XML declaration that Python doesn't know or ElementTree can't read is a LookupError or ValueError.
    except (ET.ParseError, LookupError, ValueError) as err:
        raise FinaviaError(f"Finavia's answer isn't XML: {err}") from err
    if root.tag != f"{NS}flights":
        raise FinaviaError(f"Finavia's answer isn't a list of flights but {root.tag}")
    return root


def departures(board: ET.Element, language: str, count: int, now: datetime) -> list[Departure]:
    """The next departures in order of their estimated time, without the flights that have left or are past, the count of
    those not cancelled (see counted)."""
    found = [
        departure
        for flight in board.iterfind(f"{NS}dep/{NS}body/{NS}flight")
        if (departure := parse_departure(flight, language)) and departure.estimated >= now - DEPARTURE_PAST
    ]
    found.sort(key=lambda departure: departure.estimated)
    return counted(found, count)


def arrivals(board: ET.Element, language: str, count: int, now: datetime) -> list[Departure]:
    """The next `count` arrivals still to come and not cancelled (see counted), and besides them the latest two that are
    over (see is_over) within half an hour, in order of their estimated time, so neither cancellations nor those that are
    over push the next arrival off the list."""
    found = [
        arrival
        for flight in board.iterfind(f"{NS}arr/{NS}body/{NS}flight")
        if (arrival := parse_arrival(flight, language)) and arrival.estimated >= now - ARRIVAL_PAST
    ]
    found.sort(key=lambda arrival: arrival.estimated)
    over = [arrival for arrival in found if is_over(arrival, now)]
    coming = [arrival for arrival in found if not is_over(arrival, now)]
    return sorted(over[-LANDED_LISTED:] + counted(coming, count), key=lambda arrival: arrival.estimated)


def counted(flights: list[Departure], count: int) -> list[Departure]:
    """The first `count` flights not cancelled, in order, with the cancelled ones among them, so a run of cancellations
    never pushes the next flight that flies off the list. When fewer than `count` aren't cancelled, as in a strike, the cancelled
    ones after the last of them fill the list up to `count`."""
    last, counting = -1, 0
    for index, item in enumerate(flights):
        if counting >= count:
            break
        if not item.cancelled:
            last, counting = index, counting + 1
    listed = flights[: last + 1]
    if counting >= count:
        return listed
    return listed + flights[last + 1 :][: max(count - len(listed), 0)]


def is_over(arrival: Departure, now: datetime) -> bool:
    """A flight that has landed, or one cancelled and past its time: listed besides the count, the latest two."""
    return arrival.arrived or (arrival.cancelled and arrival.estimated < now)


def parse_departure(flight: ET.Element, language: str) -> Departure | None:
    """One departure, or None for a flight that has left, which can't be boarded, or one without a number or time.

    A flight has left when its status says so or it has an actual departure time, unless it is cancelled: at the smaller
    airports the status sometimes stays empty after take-off.
    """
    text = flight_text(flight)
    line, scheduled, status = text("fltnr"), parse_time(text("sdt")), text("prt")
    # A cancelled flight hasn't left or landed, whatever else Finavia's data says.
    if not line or scheduled is None or (status != CANCELLED and (status == DEPARTED or text("act_d"))):
        return None
    estimate = parse_time(text("pest_d"))
    return Departure(
        id=f"flight:{scheduled.date().isoformat()}/{line}",
        line=line,
        headsign=", ".join(leg_names(text, language)) or None,
        scheduled=scheduled,
        estimated=estimate or scheduled,
        realtime=estimate is not None,
        platform=text("gate") or None,
        cancelled=status == CANCELLED,
        notice=notice(text, status, language),
    )


def parse_arrival(flight: ET.Element, language: str) -> Departure | None:
    """One arrival, or None for one without a number or time.

    A flight has landed when its status says so or it has a landing time, unless it is cancelled, as a departure has
    left. A landing time is its
    estimated time, as Finavia's own estimate stays as it was and can be minutes off. The route usually lists where
    it comes from, but a flight through the airport can list its whole
    way, the airport itself included (FRA, KTT, EVE landing at Kittilä), so only the legs before the airport count.
    """
    text = flight_text(flight)
    line, scheduled, status = text("fltnr"), parse_time(text("sdt")), text("prt")
    if not line or scheduled is None:
        return None
    # A cancelled flight hasn't landed, whatever else Finavia's data says, so its landing time doesn't count.
    landing = parse_time(text("act_d")) if status != CANCELLED else None
    estimate = landing or parse_time(text("pest_d"))
    codes = [text(f"route_{leg}") for leg in LEGS]
    here = text("h_apt")
    legs = range(1, codes.index(here) + 1) if here and here in codes else LEGS
    return Departure(
        # A flight through the airport has the same number arriving and leaving, so arrivals have ids of their own.
        id=f"arrival:{scheduled.date().isoformat()}/{line}",
        line=line,
        headsign=", ".join(leg_names(text, language, legs)) or None,
        scheduled=scheduled,
        estimated=estimate or scheduled,
        realtime=estimate is not None,
        platform=text("bltarea") or None,
        cancelled=status == CANCELLED,
        notice=notice(text, status, language),
        arrived=(status == LANDED or landing is not None) and status != CANCELLED,
    )


def flight_text(flight: ET.Element) -> Callable[[str], str]:
    def text(tag: str) -> str:
        return (flight.findtext(NS + tag) or "").strip()

    return text


def notice(text: Callable[[str], str], status: str, language: str) -> str | None:
    """The status in the language, or in English when Finavia has no text in it, as it sometimes has no Finnish place name."""
    if status in NO_NOTICE:
        return None
    return text(STATUS_FIELDS.get(language, "prt")) or status or None


def leg_names(text: Callable[[str], str], language: str, legs: range = LEGS) -> list[str]:
    """The legs' places, each in Finnish when asked and Finavia has it, otherwise in English, or its IATA code."""
    names = []
    for leg in legs:
        finnish = text(f"route_n_fi_{leg}") if language == "fi" else ""
        if name := finnish or text(f"route_n_{leg}") or text(f"route_{leg}"):
            names.append(name)
    return names


def parse_time(value: str) -> datetime | None:
    """Finavia's times are ISO 8601 in UTC, "2026-10-23T06:30:00Z"."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None
