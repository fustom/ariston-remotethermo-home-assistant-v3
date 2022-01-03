"""Support for Ariston sensors."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .entity import AristonEntity
from .const import ARISTON_BINARY_SENSOR_TYPES, COORDINATOR, DOMAIN
from .coordinator import DeviceDataUpdateCoordinator
from .ariston import DeviceAttribute, PropertyType

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
        COORDINATOR
    ]

    ariston_binary_sensors: list[AristonBinarySensor] = []
    for description in ARISTON_BINARY_SENSOR_TYPES:
        ariston_binary_sensors.append(AristonBinarySensor(coordinator, description))

    async_add_entities(ariston_binary_sensors)


class AristonBinarySensor(AristonEntity, BinarySensorEntity):
    """Base class for specific ariston binary sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)

        self.entity_description = description
        self.coordinator = coordinator

    @property
    def unique_id(self):
        """Return the unique id."""
        return (
            f"{self.coordinator.device.attributes[DeviceAttribute.GW_ID]}-{self.name}"
        )

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return self.coordinator.device.get_item_by_id(
            self.entity_description.key, PropertyType.VALUE
        )
