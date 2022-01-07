"""Support for Ariston sensors."""
from __future__ import annotations

import logging
import sys

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .entity import AristonEntity
from .const import ARISTON_NUMBER_TYPES, DOMAIN, AristonNumberEntityDescription
from .coordinator import DeviceDataUpdateCoordinator, DeviceEnergyUpdateCoordinator
from .ariston import DeviceAttribute

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_numbers: list[NumberEntity] = []

    for description in ARISTON_NUMBER_TYPES:
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator = (
            hass.data[DOMAIN][entry.unique_id][description.coordinator]
        )
        if coordinator.device.are_device_features_available(
            description.device_features, description.extra_energy_feature
        ):
            ariston_numbers.append(
                AristonNumber(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_numbers)


class AristonNumber(AristonEntity, NumberEntity):
    """Base class for specific ariston binary sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator,
        description: AristonNumberEntityDescription,
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
    def value(self):
        """Return the current value"""
        return self.coordinator.device.consumptions_settings[
            self.entity_description.key
        ]

    # Should be removed after HA release the new NumberEntityDescription (https://github.com/home-assistant/core/pull/61100/)
    @property
    def min_value(self) -> float:
        return 0

    # Should be removed after HA release the new NumberEntityDescription (https://github.com/home-assistant/core/pull/61100/)
    @property
    def max_value(self) -> float:
        return sys.maxsize

    # Should be removed after HA release the new NumberEntityDescription (https://github.com/home-assistant/core/pull/61100/)
    @property
    def step(self) -> float:
        return 0.01

    async def async_set_value(self, value: float):
        """Update the current value."""
        await self.coordinator.device.async_set_consumptions_settings(
            self.entity_description.key, value
        )
