"""Support for Ariston sensors."""
from __future__ import annotations

import logging

from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity

from .entity import AristonEntity
from .const import (
    ARISTON_SENSOR_TYPES,
    DOMAIN,
    AristonSensorEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston sensors from config entry."""
    ariston_sensors = []

    for description in ARISTON_SENSOR_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]
        if (
            coordinator
            and coordinator.device
            and coordinator.device.are_device_features_available(
                description.device_features,
                description.system_types,
                description.whe_types,
            )
        ):
            ariston_sensors.append(
                AristonSensor(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_sensors)


class AristonSensor(AristonEntity, SensorEntity):
    """Base class for specific ariston sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description)

    @property
    def native_value(self):
        """Return value of sensor."""
        return self.entity_description.get_native_value(self)

    @property
    def native_unit_of_measurement(self):
        """Return the nateive unit of measurement"""
        if self.entity_description.get_native_unit_of_measurement is not None:
            return self.entity_description.get_native_unit_of_measurement(self)

        if self.entity_description.native_unit_of_measurement is not None:
            return self.entity_description.native_unit_of_measurement

    @property
    def last_reset(self) -> datetime | None:
        if self.entity_description.get_last_reset is not None:
            return self.entity_description.get_last_reset(self)
