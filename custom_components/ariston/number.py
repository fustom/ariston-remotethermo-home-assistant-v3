"""Support for Ariston sensors."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ARISTON_NUMBER_TYPES, DOMAIN, AristonNumberEntityDescription
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_numbers: list[AristonNumber] = []

    for description in ARISTON_NUMBER_TYPES:
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
            if description.zone:
                for zone_number in coordinator.device.zone_numbers:
                    ariston_numbers.append(
                        AristonNumber(
                            coordinator,
                            description,
                            zone_number,
                        )
                    )
            else:
                ariston_numbers.append(AristonNumber(coordinator, description))

    async_add_entities(ariston_numbers)


class AristonNumber(AristonEntity, NumberEntity):
    """Base class for specific ariston binary sensors."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonNumberEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description, zone)

    @property
    def name(self):
        """Return the name of the entity."""
        if self.zone:
            return f"{self.entity_description.name} {self.zone}"
        return self.entity_description.name

    @property
    def native_value(self):
        """Return the current value."""
        return self.entity_description.get_native_value(self)

    @property
    def native_min_value(self):
        """Return the minimum value."""
        if self.entity_description.get_native_min_value is not None:
            return self.entity_description.get_native_min_value(self)

        return self.entity_description.native_min_value

    @property
    def native_max_value(self):
        """Return the maximum value."""
        if self.entity_description.get_native_max_value is not None:
            return self.entity_description.get_native_max_value(self)

        return self.entity_description.native_max_value

    @property
    def native_step(self):
        """Return the step value."""
        if self.entity_description.get_native_step is not None:
            return self.entity_description.get_native_step(self)

        return self.entity_description.native_step

    async def async_set_native_value(self, value: float):
        """Update the current value."""
        await self.entity_description.set_native_value(self, value)
        self.async_write_ha_state()
