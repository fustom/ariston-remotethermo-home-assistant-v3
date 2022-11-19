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
            description.system_types,
        ):
            if description.zone:
                for zone_number in coordinator.device.get_zone_numbers():
                    ariston_numbers.append(
                        AristonNumber(
                            coordinator,
                            description,
                            zone_number,
                        )
                    )
            else:
                ariston_numbers.append(AristonNumber(coordinator, description, None))

    async_add_entities(ariston_numbers)


class AristonNumber(AristonEntity, NumberEntity):
    """Base class for specific ariston binary sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonNumberEntityDescription,
        zone: int,
    ) -> None:
        super().__init__(coordinator, description, zone)

    @property
    def name(self):
        """Return the name of the entity"""
        if self.entity_description.zone:
            return f"{self.entity_description.name} {self.zone}"
        return self.entity_description.name

    @property
    def native_value(self):
        """Return the current value"""
        if self.entity_description.zone:
            return getattr(self.device, self.entity_description.getter.__name__)(
                self.zone
            )
        return getattr(self.device, self.entity_description.getter.__name__)()

    @property
    def native_min_value(self):
        """Return the minimum value"""
        if self.entity_description.min is not None:
            if self.entity_description.zone:
                return getattr(self.device, self.entity_description.min.__name__)(
                    self.zone
                )
            return getattr(self.device, self.entity_description.min.__name__)()

        return self.entity_description.native_min_value

    @property
    def native_max_value(self):
        """Return the maximum value"""
        if self.entity_description.max is not None:
            if self.entity_description.zone:
                return getattr(self.device, self.entity_description.max.__name__)(
                    self.zone
                )
            return getattr(self.device, self.entity_description.max.__name__)()

        return self.entity_description.native_max_value

    @property
    def native_step(self):
        """Return the step value"""
        if self.entity_description.getstep is not None:
            if self.entity_description.zone:
                return getattr(self.device, self.entity_description.getstep.__name__)(
                    self.zone
                )
            return getattr(self.device, self.entity_description.getstep.__name__)()

        return self.entity_description.native_step

    async def async_set_native_value(self, value: float):
        """Update the current value."""
        if self.entity_description.zone:
            await getattr(self.device, self.entity_description.setter.__name__)(
                value, self.zone
            )
        else:
            await getattr(self.device, self.entity_description.setter.__name__)(value)
        self.async_write_ha_state()
