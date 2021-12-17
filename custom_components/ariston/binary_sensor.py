"""Suppoort for Ariston sensors."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeviceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id]

    ariston_binary_sensors = []
    ariston_binary_sensors.append(IsFlameOnBinarySensor(coordinator))

    async_add_entities(ariston_binary_sensors)


class AristonBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base class for specific ariston binary sensors"""

    def __init__(
        self, coordinator: DeviceDataUpdateCoordinator, name: str, device_class: str
    ) -> None:
        super().__init__(coordinator)

        self.coordinator = coordinator
        self._name = name
        self._device_class = device_class

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self.coordinator.device.gw_id}-{self.name}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def device_class(self):
        return self._device_class


class IsFlameOnBinarySensor(AristonBinarySensor):
    """Is flame on binary sensor class"""

    def __init__(self, coordinator: DeviceDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "Is flame on", None)

    @property
    def icon(self):
        return "mdi:fire"

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return self.coordinator.device.is_flame_on
