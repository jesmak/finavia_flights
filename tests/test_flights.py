"""Parsing Finavia's departures and arrivals XML into the departures format."""

from __future__ import annotations

import pytest

from custom_components.finavia_flights.api import FinaviaError
from custom_components.finavia_flights.flights import arrivals, departures, parse_board

from .conftest import EMPTY_XML, HELSINKI_XML, IVALO, KITTILA, NOW, OULU, STOCKHOLM, arrivals_xml, board_xml, departures_xml, flight

LATER = "2026-03-14T11:00:00Z"


def one(xml_flight: dict[str, str], language: str = "fi") -> list[dict]:
    return [departure.as_attribute() for departure in departures(parse_board(departures_xml(xml_flight)), language, 10, NOW)]


def test_helsinki_departures() -> None:
    found = [departure.as_attribute() for departure in departures(parse_board(HELSINKI_XML), "fi", 10, NOW)]
    assert found == [
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
            "cancelled, with an actual time all the same, hasn't left",
            flight("AY1", LATER, OULU, status="Cancelled", code="CNL", actual="2026-03-14T09:58:00Z"),
            expect(cancelled=True),
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
    assert [departure.line for departure in departures(parse_board(xml), "fi", 2, NOW)] == ["AY1", "AY2"]


def test_flights_without_a_number_or_time_are_skipped() -> None:
    assert one(flight("", LATER, OULU)) == []
    assert one(flight("AY1", "not a time", OULU)) == []


def test_no_flights() -> None:
    assert departures(parse_board(departures_xml()), "fi", 10, NOW) == []
    assert departures(parse_board(EMPTY_XML), "fi", 10, NOW) == [], "an unknown airport, or one with nothing today"


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
        departures(parse_board(answer), "fi", 10, NOW)


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
    [departure] = departures(parse_board(latin1), "fi", 10, NOW)
    assert departure.headsign == "Kööpenhamina"


FRANKFURT = ("FRA", "Frankfurt", "Frankfurt")
EVENES = ("EVE", "Harstad/Narvik", "Harstad/Narvik")
KITTILA_HERE = ("KTT", "Kittilä", "Kittilä")
UMEA = ("UME", "Umea", "Uumaja")
VAASA = ("VAA", "Vaasa", "Vaasa")


def arrival(**changes: object) -> dict:
    """The whole arrival the table's flight AY1 from Oulu becomes, with some fields changed; None leaves a field out."""
    later = "2026-03-14T11:00:00+00:00"
    base = {"id": "arrival:2026-03-14/AY1", "line": "AY1", "mode": "plane", "headsign": "Oulu", "scheduled": later, "estimated": later}
    found = base | {"realtime": False} | changes
    return {key: value for key, value in found.items() if value is not None}


def landed_at(minute: str, **changes: object) -> dict:
    when = f"2026-03-14T09:{minute}:00+00:00"
    return arrival(scheduled=when, estimated=when, realtime=True, delay=0, arrived=True, **changes)


# Every way an arrival's status, times and route decide whether it's listed, and everything it is then listed with. A
# landed flight is listed with its landing time when Finavia gives one, and stays half an hour past its time. The codes
# differ by airport and by direction (an estimate is EST arriving at Helsinki-Vantaa, E elsewhere), so only the texts
# may matter.
@pytest.mark.parametrize(
    ("case", "xml_flight", "expected"),
    [
        ("no status", flight("AY1", LATER, OULU), arrival()),
        (
            "landed, Helsinki's code",
            flight(
                "AY1",
                "2026-03-14T09:50:00Z",
                OULU,
                status="Landed",
                code="LAN",
                estimate="2026-03-14T09:50:00Z",
                actual="2026-03-14T09:50:00Z",
                hall="2A",
            ),
            landed_at("50", platform="2A"),
        ),
        (
            "landed, other airports' code",
            flight(
                "AY1",
                "2026-03-14T09:50:00Z",
                OULU,
                airport="RVN",
                status="Landed",
                code="A",
                estimate="2026-03-14T09:50:00Z",
                actual="2026-03-14T09:50:00Z",
            ),
            landed_at("50"),
        ),
        (
            "landed, Finavia's estimate minutes off the landing time",
            flight(
                "AY1",
                "2026-03-14T09:50:00Z",
                OULU,
                status="Landed",
                code="LAN",
                estimate="2026-03-14T09:55:00Z",
                actual="2026-03-14T09:43:00Z",
            ),
            arrival(scheduled="2026-03-14T09:50:00+00:00", estimated="2026-03-14T09:43:00+00:00", realtime=True, delay=-420, arrived=True),
        ),
        (
            "landed 31 minutes ago, Finavia's estimate later",
            flight(
                "AY1",
                "2026-03-14T09:30:00Z",
                OULU,
                status="Landed",
                code="LAN",
                estimate="2026-03-14T09:38:00Z",
                actual="2026-03-14T09:29:00Z",
            ),
            None,
        ),
        (
            "landed by its status, with an estimate but no landing time",
            flight("AY1", "2026-03-14T09:50:00Z", OULU, status="Landed", code="LAN", estimate="2026-03-14T09:47:00Z"),
            arrival(scheduled="2026-03-14T09:50:00+00:00", estimated="2026-03-14T09:47:00+00:00", realtime=True, delay=-180, arrived=True),
        ),
        (
            "a landing time with no status",
            {**flight("AY1", "2026-03-14T09:50:00Z", OULU), "act_d": "2026-03-14T09:50:00Z"},
            landed_at("50"),
        ),
        (
            "landed by its status, with no times",
            flight("AY1", "2026-03-14T09:50:00Z", OULU, status="Landed", code="LAN"),
            arrival(scheduled="2026-03-14T09:50:00+00:00", estimated="2026-03-14T09:50:00+00:00", arrived=True),
        ),
        (
            "landed exactly half an hour ago",
            flight(
                "AY1",
                "2026-03-14T09:30:00Z",
                OULU,
                status="Landed",
                code="LAN",
                estimate="2026-03-14T09:30:00Z",
                actual="2026-03-14T09:30:00Z",
            ),
            landed_at("30"),
        ),
        (
            "landed 31 minutes ago",
            flight(
                "AY1",
                "2026-03-14T09:29:00Z",
                OULU,
                status="Landed",
                code="LAN",
                estimate="2026-03-14T09:29:00Z",
                actual="2026-03-14T09:29:00Z",
            ),
            None,
        ),
        (
            "early",
            flight("AY1", LATER, OULU, status="Estimated arrival", code="EST", estimate="2026-03-14T10:45:00Z", hall="2B"),
            arrival(estimated="2026-03-14T10:45:00+00:00", realtime=True, delay=-900, platform="2B"),
        ),
        (
            "estimated, other airports' code",
            flight("AY1", LATER, OULU, airport="RVN", status="Estimated arrival", code="E", estimate="2026-03-14T11:10:00Z"),
            arrival(estimated="2026-03-14T11:10:00+00:00", realtime=True, delay=600),
        ),
        ("approaching", flight("AY1", LATER, OULU, status="Approaching", code="ETA"), arrival(notice="Lähestyy")),
        ("cancelled, Helsinki's code", flight("AY1", LATER, OULU, status="Cancelled", code="CNL"), arrival(cancelled=True)),
        (
            "cancelled, other airports' code",
            flight("AY1", LATER, OULU, airport="RVN", status="Cancelled", code="C"),
            arrival(cancelled=True),
        ),
        ("cancelled an hour ago", flight("AY1", "2026-03-14T09:00:00Z", OULU, status="Cancelled", code="CNL"), None),
        ("no status, scheduled 40 minutes ago", flight("AY1", "2026-03-14T09:20:00Z", OULU), None),
        ("a gate but no hall", flight("AY1", LATER, OULU, gate="19"), arrival()),
        ("stops on the way", flight("AY1", LATER, UMEA, VAASA), arrival(headsign="Uumaja, Vaasa")),
        ("a route that starts at the airport itself", flight("AY1", LATER, OULU, IVALO, airport="OUL"), arrival(headsign=None)),
        (
            "through the airport itself",
            flight("AY1", LATER, FRANKFURT, KITTILA_HERE, EVENES, airport="KTT"),
            arrival(headsign="Frankfurt"),
        ),
    ],
)
def test_which_arrivals_are_listed(case: str, xml_flight: dict[str, str], expected: dict | None) -> None:
    found = [flight.as_attribute() for flight in arrivals(parse_board(arrivals_xml(xml_flight)), "fi", 10, NOW)]
    assert found == ([] if expected is None else [expected]), case


@pytest.mark.parametrize(("language", "notice"), [("fi", "Lähestyy"), ("sv", "Landar"), ("en", "Approaching")])
def test_an_arrivals_status_follows_the_language(language: str, notice: str) -> None:
    [found] = arrivals(parse_board(arrivals_xml(flight("AY1", LATER, STOCKHOLM, status="Approaching"))), language, 10, NOW)
    assert (found.headsign, found.notice) == ("Tukholma" if language == "fi" else "Stockholm", notice)


def test_one_answer_holds_both_directions() -> None:
    board = parse_board(board_xml((flight("AY2", LATER, OULU),), (flight("AY1", LATER, OULU),)))
    assert [found.id for found in departures(board, "fi", 10, NOW)] == ["flight:2026-03-14/AY2"]
    assert [found.id for found in arrivals(board, "fi", 10, NOW)] == ["arrival:2026-03-14/AY1"]


def test_a_flight_through_the_airport_has_two_ids() -> None:
    """The same number lands and leaves again, so a list of both needs the two told apart."""
    board = parse_board(board_xml((flight("AY1", LATER, OULU),), (flight("AY1", "2026-03-14T10:40:00Z", IVALO),)))
    [leaving], [landing] = departures(board, "fi", 10, NOW), arrivals(board, "fi", 10, NOW)
    assert leaving.id != landing.id


# The count is of the arrivals still to come. The latest two landed are listed besides them, and don't take its places.
@pytest.mark.parametrize(
    ("count", "landed", "expected"),
    [
        (1, 1, ["AY1", "AY5"]),
        (1, 3, ["AY2", "AY3", "AY5"]),
        (2, 2, ["AY1", "AY2", "AY5", "AY6"]),
        (3, 0, ["AY5", "AY6", "AY7"]),
        (5, 3, ["AY2", "AY3", "AY5", "AY6", "AY7"]),
    ],
)
def test_the_count_is_of_the_arrivals_still_to_come(count: int, landed: int, expected: list[str]) -> None:
    times = ("35", "40", "45")[:landed]
    flights = [
        flight(f"AY{n}", f"2026-03-14T09:{m}:00Z", OULU, status="Landed", code="LAN", actual=f"2026-03-14T09:{m}:00Z")
        for n, m in enumerate(times, 1)
    ]
    flights += [flight(f"AY{n}", f"2026-03-14T10:{m}:00Z", OULU) for n, m in ((5, 10), (6, 20), (7, 30))]
    assert [found.line for found in arrivals(parse_board(arrivals_xml(*flights)), "fi", count, NOW)] == expected


def test_only_the_latest_two_over_are_listed_and_a_cancelled_one_never_lands() -> None:
    landed = [
        flight(f"AY{n}", f"2026-03-14T09:{m}:00Z", OULU, status="Landed", code="LAN", actual=f"2026-03-14T09:{m}:00Z")
        for n, m in ((1, 35), (2, 40), (3, 45), (4, 50))
    ]
    coming = [flight(f"AY{n}", f"2026-03-14T10:{m}:00Z", OULU) for n, m in ((5, 10), (6, 20), (7, 30))]
    # A cancelled flight with a landing time all the same still hasn't landed.
    cancelled = flight("AY8", "2026-03-14T09:55:00Z", OULU, status="Cancelled", code="CNL", actual="2026-03-14T09:55:00Z")
    found = arrivals(parse_board(arrivals_xml(*landed, cancelled, *coming)), "fi", 3, NOW)
    assert [f.line for f in found] == ["AY4", "AY8", "AY5", "AY6", "AY7"], "the latest two over, and three to come"
    assert (found[1].cancelled, found[1].arrived, found[1].realtime) == (True, False, False), "its landing time doesn't count"


def test_a_cancelled_arrival_past_its_time_is_over_and_listed_besides_the_count() -> None:
    cancelled = flight("AY1", "2026-03-14T09:40:00Z", OULU, status="Cancelled", code="CNL")
    coming = [flight(f"AY{n}", f"2026-03-14T10:{m}:00Z", OULU) for n, m in ((5, 10), (6, 20), (7, 30))]
    found = arrivals(parse_board(arrivals_xml(cancelled, *coming)), "fi", 2, NOW)
    assert [f.line for f in found] == ["AY1", "AY5", "AY6"]


# The count is of the flights not cancelled. Cancelled ones before the last counted are listed too, in their place by
# time, so a run of cancellations never pushes the next flight that flies off the list. Arrivals that are over, the
# latest two, are listed besides them as before.
@pytest.mark.parametrize(
    ("direction", "count", "flights", "expected"),
    [
        ("departures", 1, [("AY1", "10:05", True), ("AY2", "10:10", False), ("AY3", "10:20", False)], ["AY1", "AY2"]),
        (
            "departures",
            2,
            [("AY1", "10:05", False), ("AY2", "10:10", True), ("AY3", "10:20", False), ("AY4", "10:30", True)],
            ["AY1", "AY2", "AY3"],
        ),
        ("departures", 2, [("AY1", "10:05", True), ("AY2", "10:10", True)], ["AY1", "AY2"]),
        ("departures", 1, [("AY1", "10:05", False), ("AY2", "10:10", True)], ["AY1"]),
        ("departures", 2, [("AY1", "10:05", False), ("AY2", "10:10", True), ("AY3", "10:20", True)], ["AY1", "AY2"]),
        ("departures", 2, [(f"AY{n}", f"10:{n:02d}", True) for n in range(1, 6)], ["AY1", "AY2"]),
        (
            "departures",
            3,
            [("AY1", "10:01", True), ("AY2", "10:02", False), ("AY3", "10:03", True), ("AY4", "10:04", True), ("AY5", "10:05", True)],
            ["AY1", "AY2", "AY3"],
        ),
        ("arrivals", 1, [("AY1", "10:05", True), ("AY2", "10:10", True), ("AY3", "10:20", True)], ["AY1"]),
        (
            "departures",
            2,
            [("AY1", "10:01", True), ("AY2", "10:02", True), ("AY3", "10:03", False), ("AY4", "10:04", True), ("AY5", "10:05", True)],
            ["AY1", "AY2", "AY3"],
        ),
        (
            "arrivals",
            2,
            [("AY1", "10:01", True), ("AY2", "10:02", True), ("AY3", "10:03", False), ("AY4", "10:04", True), ("AY5", "10:05", True)],
            ["AY1", "AY2", "AY3"],
        ),
        ("arrivals", 1, [("AY9", "09:50", True), ("AY1", "10:05", True), ("AY2", "10:10", True), ("AY3", "10:20", True)], ["AY9", "AY1"]),
        ("departures", 2, [], []),
        ("arrivals", 2, [], []),
        ("arrivals", 1, [("AY1", "10:05", True), ("AY2", "10:10", False), ("AY3", "10:20", False)], ["AY1", "AY2"]),
        ("arrivals", 1, [("AY9", "09:50", True), ("AY1", "10:00", True), ("AY2", "10:10", False)], ["AY9", "AY1", "AY2"]),
        (
            "arrivals",
            2,
            [("AY1", "10:05", False), ("AY2", "10:10", True), ("AY3", "10:20", False), ("AY4", "10:30", True)],
            ["AY1", "AY2", "AY3"],
        ),
    ],
)
def test_the_count_is_of_the_flights_not_cancelled(direction: str, count: int, flights: list, expected: list[str]) -> None:
    built = [
        flight(line, f"2026-03-14T{time}:00Z", OULU, **({"status": "Cancelled", "code": "CNL"} if cancelled else {}))
        for line, time, cancelled in flights
    ]
    if direction == "departures":
        found = departures(parse_board(departures_xml(*built)), "fi", count, NOW)
    else:
        found = arrivals(parse_board(arrivals_xml(*built)), "fi", count, NOW)
    assert [item.line for item in found] == expected


def test_arrivals_in_order_and_counted() -> None:
    xml = arrivals_xml(*(flight(f"AY{n}", f"2026-03-14T1{n}:00:00Z", IVALO) for n in (3, 1, 2)))
    assert [found.line for found in arrivals(parse_board(xml), "fi", 2, NOW)] == ["AY1", "AY2"]


def test_an_answer_without_arrivals_has_none() -> None:
    assert arrivals(parse_board(departures_xml(flight("AY1", LATER, OULU))), "fi", 10, NOW) == []
    assert arrivals(parse_board(EMPTY_XML), "fi", 10, NOW) == []
