"""One coordinator per airport (config subentry), fetching its departures, arrivals or both every ten minutes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FinaviaAuthError, FinaviaClient, FinaviaError
from .const import (
    API_KINDS,
    CONF_AIRPORT,
    CONF_DEPARTURES,
    CONF_DIRECTION,
    DEFAULT_DEPARTURES,
    DIRECTION_ARRIVALS,
    DIRECTION_DEPARTURES,
    DIRECTION_SENSORS,
    DOMAIN,
    UPDATE_INTERVAL,
    language_of,
)
from .flights import Departure, arrivals, departures, parse_board

_LOGGER = logging.getLogger(__name__)


@dataclass
class FinaviaRuntimeData:
    client: FinaviaClient
    coordinators: dict[str, AirportCoordinator] = field(default_factory=dict)


type FinaviaConfigEntry = ConfigEntry[FinaviaRuntimeData]


class AirportCoordinator(DataUpdateCoordinator[dict[str, list[Departure]]]):
    """One airport's flights by direction, "departures" or "arrivals", fetched in one request whichever it has."""

    config_entry: FinaviaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FinaviaConfigEntry, subentry: ConfigSubentry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {subentry.title}", update_interval=UPDATE_INTERVAL)
        self.subentry = subentry
        self.airport = str(subentry.data[CONF_AIRPORT])
        self.count = int(subentry.data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES))
        # A subentry from before arrivals has no direction, and is departures.
        self.direction = str(subentry.data.get(CONF_DIRECTION, DIRECTION_DEPARTURES))
        self.directions = DIRECTION_SENSORS[self.direction]

    @property
    def language(self) -> str:
        return language_of(self.hass.config.language)

    async def _async_update_data(self) -> dict[str, list[Departure]]:
        try:
            xml = await self.config_entry.runtime_data.client.flights_xml(API_KINDS[self.direction], self.airport)
            board = parse_board(xml)
        except FinaviaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FinaviaError as err:
            raise UpdateFailed(str(err)) from err
        now = dt_util.utcnow()
        lists = {DIRECTION_DEPARTURES: departures, DIRECTION_ARRIVALS: arrivals}
        return {direction: lists[direction](board, self.language, self.count, now) for direction in self.directions}
