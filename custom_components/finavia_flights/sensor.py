"""A departures sensor per airport and direction.

The state is the time of the next departure that isn't cancelled, or the next arrival that isn't cancelled or landed;
the flights are in the `departures` attribute, in the departures format (docs/departures-format.md in departures-card).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DEPARTURES_VERSION, DIRECTION_ARRIVALS, DOMAIN, airport_name
from .coordinator import AirportCoordinator, FinaviaConfigEntry
from .flights import Departure


async def async_setup_entry(hass: HomeAssistant, entry: FinaviaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        async_add_entities(
            [DeparturesSensor(coordinator, direction) for direction in coordinator.directions], config_subentry_id=subentry_id
        )


class DeparturesSensor(CoordinatorEntity[AirportCoordinator], SensorEntity):
    # The flights change on every update; the next one's time is history enough.
    _unrecorded_attributes = frozenset({"departures"})
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True

    def __init__(self, coordinator: AirportCoordinator, direction: str) -> None:
        super().__init__(coordinator)
        subentry = coordinator.subentry
        self.direction = direction
        if direction == DIRECTION_ARRIVALS:
            # "Helsinki-Vantaa saapuvat"; the airport's name alone is its departures'.
            self._attr_unique_id = f"{subentry.subentry_id}_arrivals"
            self._attr_translation_key = "arrivals"
            self._attr_icon = "mdi:airplane-landing"
        else:
            # The departures' unique id is the subentry's, as it was before arrivals.
            self._attr_unique_id = subentry.subentry_id
            self._attr_name = None
            self._attr_icon = "mdi:airplane-takeoff"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Finavia",
            model_id=coordinator.airport,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def flights(self) -> list[Departure] | None:
        data = self.coordinator.data
        return None if data is None else data.get(self.direction, [])

    @property
    def native_value(self) -> datetime | None:
        flight = next((flight for flight in self.flights or [] if not flight.cancelled and not flight.arrived), None)
        return flight.estimated if flight else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        flights = self.flights
        if flights is None:
            return {}
        return {
            "departures_version": DEPARTURES_VERSION,
            "direction": self.direction,
            "stop_id": self.coordinator.airport,
            "stop_name": airport_name(self.coordinator.airport, self.coordinator.language),
            "departures": [flight.as_attribute() for flight in flights],
        }
