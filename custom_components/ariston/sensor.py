"""Suppoort for Ariston sensors."""
from __future__ import annotations

import logging

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription

from .ariston import PropertyType
from .const import ARISTON_SENSOR_TYPES, DOMAIN
from .coordinator import DeviceDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston sensors from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id]

    ariston_sensors: list[AristonSensor] = []
    for description in ARISTON_SENSOR_TYPES:
        ariston_sensors.append(
            AristonSensor(
                coordinator,
                description,
            )
        )

    async_add_entities(ariston_sensors)


class AristonSensor(CoordinatorEntity, SensorEntity):
    """Base class for specific ariston sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.entity_description = description
        self.coordinator = coordinator

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self.coordinator.device.gw_id}-{self.name}"

    @property
    def native_value(self):
        """Return value of sensor."""
        return self.coordinator.device.get_item_by_id(
            self.entity_description.key, PropertyType.VALUE
        )

    @property
    def native_unit_of_measurement(self):
        return self.coordinator.device.get_item_by_id(
            self.entity_description.key, PropertyType.UNIT
        )
