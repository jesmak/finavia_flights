"""One coordinator per airport (config subentry), fetching its departures every ten minutes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FinaviaAuthError, FinaviaClient, FinaviaError
from .const import CONF_AIRPORT, CONF_DEPARTURES, DEFAULT_DEPARTURES, DOMAIN, UPDATE_INTERVAL, language_of
from .flights import Departure, parse_departures

_LOGGER = logging.getLogger(__name__)


@dataclass
class FinaviaRuntimeData:
    client: FinaviaClient
    coordinators: dict[str, AirportCoordinator] = field(default_factory=dict)


type FinaviaConfigEntry = ConfigEntry[FinaviaRuntimeData]


class AirportCoordinator(DataUpdateCoordinator[list[Departure]]):
    """The next departures from one airport."""

    config_entry: FinaviaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FinaviaConfigEntry, subentry: ConfigSubentry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {subentry.title}", update_interval=UPDATE_INTERVAL)
        self.subentry = subentry
        self.airport = str(subentry.data[CONF_AIRPORT])
        self.count = int(subentry.data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES))

    @property
    def language(self) -> str:
        return language_of(self.hass.config.language)

    async def _async_update_data(self) -> list[Departure]:
        try:
            xml = await self.config_entry.runtime_data.client.departures_xml(self.airport)
            return parse_departures(xml, self.language, self.count, dt_util.utcnow())
        except FinaviaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FinaviaError as err:
            raise UpdateFailed(str(err)) from err
