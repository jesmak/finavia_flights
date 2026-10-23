"""The departures sensor."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.finavia_flights.const import API_URL, DOMAIN, language_of
from custom_components.finavia_flights.sensor import DeparturesSensor

from .conftest import EMPTY_XML, NOW, OULU, STOCKHOLM, departures_xml, flight


async def setup_helsinki(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Finavia",
        data={"api_key": "test-key"},
        subentries_data=[
            ConfigSubentryData(subentry_type="airport", title="Helsinki-Vantaa", unique_id=None, data={"airport": "HEL", "departures": 10})
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_departures_sensor(hass: HomeAssistant, finavia: AiohttpClientMocker, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)
    hass.config.language = "fi"
    await setup_helsinki(hass)

    state = hass.states.get("sensor.helsinki_vantaa")
    assert state.state == "2026-03-14T10:30:00+00:00", "the next departure that isn't cancelled"
    assert state.attributes["device_class"] == "timestamp"
    assert state.attributes["departures_version"] == 1
    assert state.attributes["stop_id"] == "HEL"
    assert state.attributes["stop_name"] == "Helsinki-Vantaa"
    assert state.attributes["attribution"] == "Finavia"
    assert [departure["line"] for departure in state.attributes["departures"]] == ["AY9003", "AY9007", "AY9005"]
    assert finavia.mock_calls[0][3]["app_key"] == "test-key"


async def test_the_departures_stay_out_of_the_recorder() -> None:
    assert DeparturesSensor._unrecorded_attributes == frozenset({"departures"})


async def test_only_cancelled_departures(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL.format(airport="HEL"), text=departures_xml(flight("AY1", "2026-03-14T11:00:00Z", OULU, status="Cancelled")))
    await setup_helsinki(hass)
    state = hass.states.get("sensor.helsinki_vantaa")
    assert state.state == STATE_UNKNOWN
    assert len(state.attributes["departures"]) == 1


async def test_a_failed_fetch_makes_it_unavailable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(API_URL.format(airport="HEL"), status=500)
    await setup_helsinki(hass)
    assert hass.states.get("sensor.helsinki_vantaa").state == STATE_UNAVAILABLE


async def test_an_answer_that_isnt_xml_makes_it_unavailable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(API_URL.format(airport="HEL"), text="<html>Maintenance")
    await setup_helsinki(hass)
    assert hass.states.get("sensor.helsinki_vantaa").state == STATE_UNAVAILABLE


async def test_a_timeout_is_named_in_the_log(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, caplog) -> None:
    aioclient_mock.get(API_URL.format(airport="HEL"), exc=TimeoutError())
    await setup_helsinki(hass)
    assert hass.states.get("sensor.helsinki_vantaa").state == STATE_UNAVAILABLE
    assert "Finavia's flights API couldn't be reached: TimeoutError" in caplog.text


async def test_an_airport_with_nothing_leaving(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(API_URL.format(airport="HEL"), text=EMPTY_XML)
    await setup_helsinki(hass)
    state = hass.states.get("sensor.helsinki_vantaa")
    assert state.state == STATE_UNKNOWN
    assert state.attributes["departures"] == []
    assert state.attributes["departures_version"] == 1


async def test_in_english(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)
    hass.config.language = "en-GB"
    xml = departures_xml(flight("AY1", "2026-03-14T11:00:00Z", STOCKHOLM, status="Go to gate", gate="22"))
    aioclient_mock.get(API_URL.format(airport="HEL"), text=xml)
    await setup_helsinki(hass)
    state = hass.states.get("sensor.helsinki_vantaa")
    assert state.attributes["stop_name"] == "Helsinki"
    [departure] = state.attributes["departures"]
    assert (departure["headsign"], departure["notice"], departure["platform"]) == ("Stockholm", "Go to gate", "22")


async def test_latin1_from_finavia(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)
    hass.config.language = "fi"
    xml = departures_xml(flight("AY1", "2026-03-14T11:00:00Z", ("CPH", "Copenhagen", "Kööpenhamina"), status="Go to gate"))
    latin1 = xml.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"').encode("iso-8859-1")
    aioclient_mock.get(API_URL.format(airport="HEL"), content=latin1, headers={"Content-Type": "application/xml"})
    await setup_helsinki(hass)
    [departure] = hass.states.get("sensor.helsinki_vantaa").attributes["departures"]
    assert departure["headsign"] == "Kööpenhamina"


@pytest.mark.parametrize(
    ("hass_language", "language"),
    [("fi", "fi"), ("sv", "sv"), ("en", "en"), ("en-GB", "en"), ("de", "en"), ("fi-FI", "fi"), ("pt-BR", "en")],
)
def test_the_language_follows_home_assistants(hass_language: str, language: str) -> None:
    assert language_of(hass_language) == language
