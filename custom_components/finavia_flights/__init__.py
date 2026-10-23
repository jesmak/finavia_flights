"""Finavia Flights: departures and arrivals at Finavia's airports as departures sensors.

The config entry holds the API key, and every airport is a config subentry with its own coordinator, and a sensor for
each of its directions, in the departures format that departures-card shows.
"""

from __future__ import annotations

import asyncio

from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FinaviaClient
from .coordinator import AirportCoordinator, FinaviaConfigEntry, FinaviaRuntimeData

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: FinaviaConfigEntry) -> bool:
    entry.runtime_data = FinaviaRuntimeData(client=FinaviaClient(async_get_clientsession(hass), entry.data[CONF_API_KEY]))
    coordinators = [AirportCoordinator(hass, entry, subentry) for subentry in entry.subentries.values()]
    for coordinator in coordinators:
        entry.runtime_data.coordinators[coordinator.subentry.subentry_id] = coordinator

    # Each airport is fetched once first, so its sensor starts with a value; one that fails is unavailable.
    await asyncio.gather(*(coordinator.async_refresh() for coordinator in coordinators))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Adding, changing or removing an airport, or changing the key, reloads everything.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: FinaviaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FinaviaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
