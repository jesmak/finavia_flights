"""A departures sensor per airport.

The state is the time of the airport's next departure that isn't cancelled; the departures are in the `departures`
attribute, in the departures format (docs/departures-format.md in departures-card).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DEPARTURES_VERSION, DOMAIN, airport_name
from .coordinator import AirportCoordinator, FinaviaConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: FinaviaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        async_add_entities([DeparturesSensor(coordinator)], config_subentry_id=subentry_id)


class DeparturesSensor(CoordinatorEntity[AirportCoordinator], SensorEntity):
    # The departures change on every update; the next departure time is history enough.
    _unrecorded_attributes = frozenset({"departures"})
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:airplane-takeoff"

    def __init__(self, coordinator: AirportCoordinator) -> None:
        super().__init__(coordinator)
        subentry = coordinator.subentry
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Finavia",
            model_id=coordinator.airport,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> datetime | None:
        departure = next((departure for departure in self.coordinator.data or [] if not departure.cancelled), None)
        return departure.estimated if departure else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        return {
            "departures_version": DEPARTURES_VERSION,
            "stop_id": self.coordinator.airport,
            "stop_name": airport_name(self.coordinator.airport, self.coordinator.language),
            "departures": [departure.as_attribute() for departure in self.coordinator.data],
        }
