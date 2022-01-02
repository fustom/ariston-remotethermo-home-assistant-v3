"""Support for Ariston sensors."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ARISTON_NUMBER_TYPES,
    COORDINATOR,
    DOMAIN,
    ENERGY_COORDINATOR,
)
from .coordinator import DeviceDataUpdateCoordinator
from .ariston import (
    DeviceAttribute,
    DeviceFeatures,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
        COORDINATOR
    ]

    ariston_numbers: list[NumberEntity] = []

    if (
        coordinator.device.features[DeviceFeatures.HAS_METERING]
        and coordinator.device.extra_energy_features
    ):
        energy_coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][
            entry.unique_id
        ][ENERGY_COORDINATOR]

        for description in ARISTON_NUMBER_TYPES:
            ariston_numbers.append(
                AristonNumber(
                    energy_coordinator,
                    description,
                )
            )

    async_add_entities(ariston_numbers)


class AristonNumber(CoordinatorEntity, NumberEntity):
    """Base class for specific ariston binary sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: NumberEntityDescription,
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

    async def async_set_value(self, value: float):
        """Update the current value."""
        await self.coordinator.device.async_set_consumptions_settings(
            self.entity_description.key, value
        )
