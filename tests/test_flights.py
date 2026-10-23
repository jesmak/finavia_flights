"""Parsing Finavia's departures XML into the departures format."""

from __future__ import annotations

import pytest

from custom_components.finavia_flights.api import FinaviaError
from custom_components.finavia_flights.flights import parse_departures

from .conftest import EMPTY_XML, HELSINKI_XML, IVALO, KITTILA, NOW, OULU, STOCKHOLM, departures_xml, flight

LATER = "2026-03-14T11:00:00Z"


def one(xml_flight: dict[str, str], language: str = "fi") -> list[dict]:
    return [departure.as_attribute() for departure in parse_departures(departures_xml(xml_flight), language, 10, NOW)]


def test_helsinki_departures() -> None:
    departures = [departure.as_attribute() for departure in parse_departures(HELSINKI_XML, "fi", 10, NOW)]
    assert departures == [
        {
            "id": "flight:2026-03-14/AY9003",
            "line": "AY9003",
            "mode": "plane",
            "headsign": "Tukholma",
            "scheduled": "2026-03-14T10:20:00+00:00",
            "estimated": "2026-03-14T10:20:00+00:00",
            "realtime": False,
            "cancelled": True,
        },
        {
            "id": "flight:2026-03-14/AY9007",
            "line": "AY9007",
            "mode": "plane",
            "headsign": "Oulu",
            "scheduled": "2026-03-14T10:30:00+00:00",
            "estimated": "2026-03-14T10:30:00+00:00",
            "realtime": False,
            "platform": "14",
            "notice": "Portille",
        },
        {
            "id": "flight:2026-03-14/AY9005",
            "line": "AY9005",
            "mode": "plane",
            "headsign": "Kittilä, Ivalo",
            "scheduled": "2026-03-14T10:10:00+00:00",
            "estimated": "2026-03-14T10:40:00+00:00",
            "realtime": True,
            "delay": 1800,
            "platform": "31B",
        },
    ], "departed AY9001 is left out, and AY9005 is ordered by its estimate, with no notice for it"


def expect(**changes: object) -> dict:
    """The whole departure the table's flight AY1 to Oulu becomes, with some fields changed; None leaves a field out."""
    later = "2026-03-14T11:00:00+00:00"
    base = {"id": "flight:2026-03-14/AY1", "line": "AY1", "mode": "plane", "headsign": "Oulu", "scheduled": later, "estimated": later}
    departure = base | {"realtime": False} | changes
    return {key: value for key, value in departure.items() if value is not None}


# Every way a flight's status, time and age decide whether it's listed, and everything it is then listed with. The codes
# differ between airports (Helsinki-Vantaa's DEP and CNL are D and C elsewhere), so only the texts may matter.
@pytest.mark.parametrize(
    ("case", "xml_flight", "expected"),
    [
        ("departed, Helsinki's code", flight("AY1", LATER, OULU, status="Departed", code="DEP"), None),
        ("departed, other airports' code", flight("AY1", LATER, OULU, airport="OUL", status="Departed", code="D"), None),
        ("departed with no status, only an actual time", flight("AY1", LATER, OULU, actual="2026-03-14T09:58:00Z"), None),
        ("cancelled, Helsinki's code", flight("AY1", LATER, OULU, status="Cancelled", code="CNL"), expect(cancelled=True)),
        (
            "cancelled, other airports' code",
            flight("AY1", LATER, OULU, airport="OUL", status="Cancelled", code="C"),
            expect(cancelled=True),
        ),
        (
            "a second code for the same status",
            flight("AY1", LATER, OULU, status="Gate closed", code="RMV", gate="12"),
            expect(platform="12", notice="Suljettu"),
        ),
        ("no status", flight("AY1", LATER, OULU), expect()),
        ("cancelled hours ago", flight("AY1", "2026-03-14T06:00:00Z", OULU, status="Cancelled", code="CNL"), None),
        ("no status, scheduled long ago", flight("AY1", "2026-03-14T07:30:00Z", OULU), None),
        (
            "scheduled exactly a minute ago",
            flight("AY1", "2026-03-14T09:59:00Z", OULU),
            expect(scheduled="2026-03-14T09:59:00+00:00", estimated="2026-03-14T09:59:00+00:00"),
        ),
        ("scheduled two minutes ago", flight("AY1", "2026-03-14T09:58:00Z", OULU), None),
        (
            "scheduled half a minute ago",
            flight("AY1", "2026-03-14T09:59:30Z", OULU),
            expect(scheduled="2026-03-14T09:59:30+00:00", estimated="2026-03-14T09:59:30+00:00"),
        ),
        (
            "scheduled in the past, estimated later",
            flight("AY1", "2026-03-14T09:30:00Z", OULU, status="Estimated", code="E", estimate="2026-03-14T10:15:00Z"),
            expect(scheduled="2026-03-14T09:30:00+00:00", estimated="2026-03-14T10:15:00+00:00", realtime=True, delay=2700),
        ),
        (
            "cancelled, with an estimate",
            flight("AY1", LATER, OULU, status="Cancelled", code="CNL", estimate="2026-03-14T11:20:00Z"),
            expect(estimated="2026-03-14T11:20:00+00:00", realtime=True, delay=1200, cancelled=True),
        ),
        (
            "an actual time with another status",
            flight("AY1", LATER, OULU, status="Gate closed", code="GTC", actual="2026-03-14T09:58:00Z"),
            None,
        ),
        (
            "scheduled later, estimated half a minute ago",
            flight("AY1", "2026-03-14T10:20:00Z", OULU, estimate="2026-03-14T09:59:30Z"),
            expect(scheduled="2026-03-14T10:20:00+00:00", estimated="2026-03-14T09:59:30+00:00", realtime=True, delay=-1230),
        ),
        (
            "no Finnish status text",
            {**flight("AY1", LATER, OULU, status="Go to gate", code="GTO"), "prt_f": ""},
            expect(notice="Go to gate"),
        ),
        ("no English status, only a Finnish one", {**flight("AY1", LATER, OULU), "prt_f": "Portille"}, expect(notice="Portille")),
        (
            "scheduled later, estimated exactly a minute ago",
            flight("AY1", "2026-03-14T10:20:00Z", OULU, estimate="2026-03-14T09:59:00Z"),
            expect(scheduled="2026-03-14T10:20:00+00:00", estimated="2026-03-14T09:59:00+00:00", realtime=True, delay=-1260),
        ),
        (
            "cancelled, with an actual time",
            flight("AY1", LATER, OULU, status="Cancelled", code="CNL", actual="2026-03-14T09:58:00Z"),
            None,
        ),
        ("estimated on time", flight("AY1", LATER, OULU, estimate=LATER), expect(realtime=True, delay=0)),
        (
            "scheduled later, estimated earlier and past",
            flight("AY1", "2026-03-14T10:20:00Z", OULU, estimate="2026-03-14T09:55:00Z"),
            None,
        ),
        (
            "scheduled later, estimated earlier but still to come",
            flight("AY1", "2026-03-14T10:20:00Z", OULU, estimate="2026-03-14T10:05:00Z"),
            expect(scheduled="2026-03-14T10:20:00+00:00", estimated="2026-03-14T10:05:00+00:00", realtime=True, delay=-900),
        ),
    ],
)
def test_which_flights_are_listed(case: str, xml_flight: dict[str, str], expected: dict | None) -> None:
    assert one(xml_flight) == ([] if expected is None else [expected]), case


@pytest.mark.parametrize(
    ("language", "headsign", "notice"),
    [("fi", "Tukholma, Kittilä", "Portille"), ("sv", "Stockholm, Kittilä", "Gå till utgång"), ("en", "Stockholm, Kittilä", "Go to gate")],
)
def test_names_and_statuses_follow_the_language(language: str, headsign: str, notice: str) -> None:
    [departure] = one(flight("AY1", LATER, STOCKHOLM, KITTILA, status="Go to gate", code="GO"), language)
    assert (departure["headsign"], departure["notice"]) == (headsign, notice)


def test_no_swedish_status_falls_back_to_english() -> None:
    [departure] = one({**flight("AY1", LATER, OULU, status="Go to gate", code="GTO"), "prt_s": ""}, "sv")
    assert departure["notice"] == "Go to gate"


def test_a_missing_name_falls_back_to_english_then_the_code() -> None:
    [departure] = one(flight("AY1", LATER, ("TRD", "Trondheim", ""), ("XYZ", "", "")))
    assert departure["headsign"] == "Trondheim, XYZ"


def test_count_limits_the_soonest() -> None:
    xml = departures_xml(*(flight(f"AY{n}", f"2026-03-14T1{n}:00:00Z", IVALO) for n in (3, 1, 2)))
    assert [departure.line for departure in parse_departures(xml, "fi", 2, NOW)] == ["AY1", "AY2"]


def test_flights_without_a_number_or_time_are_skipped() -> None:
    assert one(flight("", LATER, OULU)) == []
    assert one(flight("AY1", "not a time", OULU)) == []


def test_no_flights() -> None:
    assert parse_departures(departures_xml(), "fi", 10, NOW) == []
    assert parse_departures(EMPTY_XML, "fi", 10, NOW) == [], "an unknown airport, or one with nothing today"


@pytest.mark.parametrize(
    "answer",
    [
        "<html>Service unavailable</html",
        '{"statusCode": 500}',
        "<html><body>Maintenance</body></html>",
        b"<html>Service unavailable</html",
        b"\xff\xfe<flights/>",
        b'<?xml version="1.0" encoding="foo"?><flights xmlns="http://www.finavia.fi/FlightsService.xsd"/>',
        b'<?xml version="1.0" encoding="Shift_JIS"?><flights xmlns="http://www.finavia.fi/FlightsService.xsd"/>',
        b'<?xml version="1.0" encoding="utf-32"?><flights xmlns="http://www.finavia.fi/FlightsService.xsd"/>',
    ],
)
def test_an_answer_that_isnt_flights_fails(answer: bytes | str) -> None:
    with pytest.raises(FinaviaError):
        parse_departures(answer, "fi", 10, NOW)


# The card says "cancelled" itself and shows an estimate with its delay, so these statuses would only repeat it.
@pytest.mark.parametrize("language", ["fi", "sv", "en"])
@pytest.mark.parametrize(
    "xml_flight",
    [
        flight("AY1", LATER, OULU, status="Cancelled", code="CNL"),
        flight("AY1", LATER, OULU, airport="OUL", status="Cancelled", code="C"),
        flight("AY1", "2026-03-14T10:30:00Z", OULU, status="Estimated", code="DLU", estimate=LATER),
        flight("AY1", "2026-03-14T10:30:00Z", OULU, airport="KAO", status="Estimated", code="E", estimate=LATER),
    ],
)
def test_statuses_the_card_shows_itself_make_no_notice(xml_flight: dict[str, str], language: str) -> None:
    [departure] = one(xml_flight, language)
    assert "notice" not in departure


def test_the_xml_declaration_decides_the_encoding() -> None:
    xml = departures_xml(flight("AY1", LATER, ("CPH", "Copenhagen", "Kööpenhamina"), status="Go to gate"))
    latin1 = xml.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"').encode("iso-8859-1")
    [departure] = parse_departures(latin1, "fi", 10, NOW)
    assert departure.headsign == "Kööpenhamina"
