"""Support for Ariston sensors."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .entity import AristonEntity
from .const import (
    ARISTON_SELECT_TYPES,
    DOMAIN,
    AristonSelectEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator, DeviceEnergyUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_select: list[SelectEntity] = []

    for description in ARISTON_SELECT_TYPES:
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator = (
            hass.data[DOMAIN][entry.unique_id][description.coordinator]
        )
        if coordinator.device.are_device_features_available(
            description.device_features,
            description.extra_energy_feature,
            description.system_types,
        ):
            ariston_select.append(
                AristonSelect(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_select)


class AristonSelect(AristonEntity, SelectEntity):
    """Base class for specific ariston binary sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator,
        description: AristonSelectEntityDescription,
    ) -> None:
        super().__init__(coordinator, description)

        self.entity_description: AristonSelectEntityDescription = description

    @property
    def current_option(self):
        """Return current selected option."""
        return self.entity_description.enum_class(
            self.device.consumptions_settings.get(self.entity_description.key)
        ).name

    @property
    def options(self):
        """Return options"""
        return [c.name for c in self.entity_description.enum_class]

    async def async_select_option(self, option: str):
        await self.device.async_set_consumptions_settings(
            self.entity_description.key,
            self.entity_description.enum_class[option],
        )
        self.async_write_ha_state()
