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
from .coordinator import DeviceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_select: list[SelectEntity] = []

    for description in ARISTON_SELECT_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]
        if coordinator.device.are_device_features_available(
            description.device_features,
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
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSelectEntityDescription,
    ) -> None:
        super().__init__(coordinator, description)

    @property
    def current_option(self):
        """Return current selected option."""
        return getattr(self.device, self.entity_description.getter.__name__)()

    @property
    def options(self):
        """Return options"""
        return getattr(self.device, self.entity_description.get_options.__name__)()

    async def async_select_option(self, option: str):
        await getattr(self.device, self.entity_description.setter.__name__)(option)
        self.async_write_ha_state()
