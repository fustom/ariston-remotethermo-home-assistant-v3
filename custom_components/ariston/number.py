"""Support for Ariston sensors."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .entity import AristonEntity
from .const import ARISTON_NUMBER_TYPES, DOMAIN, AristonNumberEntityDescription
from .coordinator import DeviceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_numbers: list[NumberEntity] = []

    for description in ARISTON_NUMBER_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]
        if coordinator.device.are_device_features_available(
            description.device_features,
            description.extra_energy_feature,
            description.system_types,
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
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonNumberEntityDescription,
    ) -> None:
        super().__init__(coordinator, description)

    @property
    def native_value(self):
        """Return the current value"""
        return getattr(self.device, self.entity_description.getter.__name__)()

    @property
    def native_min_value(self):
        """Return the minimum value"""
        if self.entity_description.min is not None:
            return getattr(self.device, self.entity_description.min.__name__)()

        return self.entity_description.native_min_value

    @property
    def native_max_value(self):
        """Return the maximum value"""
        if self.entity_description.max is not None:
            return getattr(self.device, self.entity_description.max.__name__)()

        return self.entity_description.native_max_value

    async def async_set_native_value(self, value: float):
        """Update the current value."""
        await getattr(self.device, self.entity_description.setter.__name__)(value)
