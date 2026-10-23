"""The config flow, reauth and the airport subentry flow."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.finavia_flights.const import AIRPORTS, API_URL, DOMAIN

from .conftest import NOW


async def setup_entry(hass: HomeAssistant, *airports: str | tuple[str, str | None], direction: str | None = None) -> MockConfigEntry:
    """An entry with a subentry per airport, each "HEL" or ("HEL", its direction); with none it is from before arrivals."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Finavia",
        data={"api_key": "test-key"},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="airport",
                title=code,
                unique_id=None,
                data={"airport": code, "departures": 10} | ({"direction": way} if way else {}),
            )
            for code, way in ((item, direction) if isinstance(item, str) else item for item in airports)
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_the_key_is_checked_and_saved(hass: HomeAssistant, finavia: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": " test-key "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"api_key": "test-key"}
    [call] = finavia.mock_calls
    assert str(call[1]).endswith("/dep/ENF") and call[3]["app_key"] == "test-key"


async def test_a_refused_key_and_a_failed_check(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    aioclient_mock.get(API_URL.format(kind="dep", airport="ENF"), status=401)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "wrong"})
    assert result["errors"] == {"api_key": "invalid_api_key"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL.format(kind="dep", airport="ENF"), status=503)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "test-key"})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_only_one_entry(hass: HomeAssistant, finavia: AiohttpClientMocker) -> None:
    await setup_entry(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def add_airport(hass: HomeAssistant, entry: MockConfigEntry, values: dict) -> dict:
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "airport"), context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.subentries.async_configure(result["flow_id"], values)


async def test_adding_an_airport_both_ways_creates_two_sensors(hass: HomeAssistant, finavia: AiohttpClientMocker) -> None:
    hass.config.language = "fi"
    entry = await setup_entry(hass)
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "airport"), context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    options = result["data_schema"].schema["airport"].config["options"]
    assert len(options) == len(AIRPORTS)
    assert {"value": "MHQ", "label": "Maarianhamina (MHQ)"} in options
    assert result["data_schema"]({"airport": "HEL", "departures": 5})["direction"] == "both", "both by default"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"airport": "HEL", "direction": "both", "departures": 5}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    [subentry] = entry.subentries.values()
    assert (subentry.title, dict(subentry.data)) == ("Helsinki-Vantaa", {"airport": "HEL", "direction": "both", "departures": 5})
    assert hass.states.get("sensor.helsinki_vantaa").attributes["direction"] == "departures"
    assert hass.states.get("sensor.helsinki_vantaa_saapuvat").attributes["direction"] == "arrivals"
    assert [str(call[1]) for call in finavia.mock_calls if "/HEL" in str(call[1])] == [API_URL.format(kind="all", airport="HEL")], (
        "both from one request"
    )


# Each of an airport's directions can be added once, per airport: what Helsinki-Vantaa has already, and what is asked
# for. "before" is a subentry from before arrivals, which has no direction and is departures. An airport that has both,
# in one subentry or two, isn't offered at all, so nothing can be asked for it.
@pytest.mark.parametrize(
    ("there", "asked", "created"),
    [
        ((), "departures", True),
        ((), "arrivals", True),
        ((), "both", True),
        ((("OUL", "both"),), "both", True),
        ((("HEL", None),), "departures", False),
        ((("HEL", None),), "arrivals", True),
        ((("HEL", None),), "both", False),
        ((("HEL", "departures"),), "departures", False),
        ((("HEL", "departures"),), "arrivals", True),
        ((("HEL", "departures"),), "both", False),
        ((("HEL", "arrivals"),), "departures", True),
        ((("HEL", "arrivals"),), "arrivals", False),
        ((("HEL", "arrivals"),), "both", False),
        ((("HEL", "both"),), None, None),
        ((("HEL", "departures"), ("HEL", "arrivals")), None, None),
    ],
)
async def test_each_direction_once(
    hass: HomeAssistant,
    finavia: AiohttpClientMocker,
    aioclient_mock: AiohttpClientMocker,
    there: tuple,
    asked: str | None,
    created: bool | None,
) -> None:
    aioclient_mock.get(API_URL.format(kind="all", airport="OUL"), text="<flights xmlns='http://www.finavia.fi/FlightsService.xsd'/>")
    entry = await setup_entry(hass, *there)
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "airport"), context={"source": SOURCE_USER})
    offered = [option["value"] for option in result["data_schema"].schema["airport"].config["options"]]
    if asked is None:
        assert "HEL" not in offered, "an airport with both directions isn't offered"
        return
    assert "HEL" in offered
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"airport": "HEL", "direction": asked, "departures": 5}
    )
    if created:
        assert result["type"] is FlowResultType.CREATE_ENTRY
    else:
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"direction": "direction_added"}


async def test_a_subentry_from_before_arrivals_is_departures(hass: HomeAssistant, finavia: AiohttpClientMocker) -> None:
    entry = await setup_entry(hass, "HEL")
    result = await add_airport(hass, entry, {"airport": "HEL", "direction": "departures", "departures": 5})
    assert result["errors"] == {"direction": "direction_added"}


async def test_an_airport_is_offered_until_both_ways_are_added(hass: HomeAssistant, finavia: AiohttpClientMocker) -> None:
    entry = await setup_entry(hass, "HEL", direction="departures")
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "airport"), context={"source": SOURCE_USER})
    assert "HEL" in [option["value"] for option in result["data_schema"].schema["airport"].config["options"]]

    hass.config_entries.async_remove_subentry(entry, next(iter(entry.subentries)))
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(entry.entry_id)
    result = await add_airport(hass, entry, {"airport": "HEL", "direction": "both", "departures": 5})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "airport"), context={"source": SOURCE_USER})
    options = [option["value"] for option in result["data_schema"].schema["airport"].config["options"]]
    assert "HEL" not in options and len(options) == len(AIRPORTS) - 1


async def test_an_airport_added_in_another_window_meanwhile(hass: HomeAssistant, finavia: AiohttpClientMocker) -> None:
    entry = await setup_entry(hass)
    first = await hass.config_entries.subentries.async_init((entry.entry_id, "airport"), context={"source": SOURCE_USER})
    second = await hass.config_entries.subentries.async_init((entry.entry_id, "airport"), context={"source": SOURCE_USER})
    result = await hass.config_entries.subentries.async_configure(
        second["flow_id"], {"airport": "HEL", "direction": "both", "departures": 5}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    result = await hass.config_entries.subentries.async_configure(
        first["flow_id"], {"airport": "HEL", "direction": "arrivals", "departures": 5}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"direction": "direction_added"}
    assert len(entry.subentries) == 1


async def test_every_airport_added(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    for code in AIRPORTS:
        aioclient_mock.get(API_URL.format(kind="all", airport=code), text="<flights xmlns='http://www.finavia.fi/FlightsService.xsd'/>")
    entry = await setup_entry(hass, *AIRPORTS, direction="both")
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "airport"), context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "all_added"


async def test_changing_the_number_of_departures(hass: HomeAssistant, finavia: AiohttpClientMocker, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)
    entry = await setup_entry(hass, "HEL")
    [subentry] = entry.subentries.values()
    result = await entry.start_subentry_reconfigure_flow(hass, subentry.subentry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"departures": 2})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries[subentry.subentry_id].data == {"airport": "HEL", "departures": 2}
    listed = hass.states.get("sensor.hel").attributes["departures"]
    assert [departure.get("cancelled", False) for departure in listed] == [True, False, False], (
        "two that fly, and the cancelled one before them"
    )


async def test_a_new_key_by_reconfiguring(hass: HomeAssistant, finavia: AiohttpClientMocker) -> None:
    entry = await setup_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "new-key"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {"api_key": "new-key"}


async def test_a_refused_key_asks_for_a_new_one(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(API_URL.format(kind="dep", airport="HEL"), status=401)
    entry = await setup_entry(hass, "HEL")
    [flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == "reauth"

    aioclient_mock.get(API_URL.format(kind="dep", airport="ENF"), text="<flights xmlns='http://www.finavia.fi/FlightsService.xsd'/>")
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"api_key": "new-key"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {"api_key": "new-key"}
