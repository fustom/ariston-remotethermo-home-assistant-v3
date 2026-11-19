"""Support for Ariston sensors."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ARISTON_SELECT_TYPES, DOMAIN, AristonSelectEntityDescription
from .coordinator import DeviceDataUpdateCoordinator
from .entity import (
    AristonEntity,
    async_refresh_after_set,
    is_entity_description_available,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_select: list[AristonSelect] = []

    for description in ARISTON_SELECT_TYPES:
        coordinator: DeviceDataUpdateCoordinator | None = hass.data[DOMAIN][
            entry.unique_id
        ].get(description.coordinator)
        if is_entity_description_available(coordinator, description):
            ariston_select.append(
                AristonSelect(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_select)


class AristonSelect(AristonEntity, SelectEntity):
    """Base class for specific ariston binary sensors."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSelectEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)

    @property
    def current_option(self):
        """Return current selected option."""
        return self.entity_description.get_current_option(self)

    @property
    def options(self):
        """Return options."""
        return self.entity_description.get_options(self)

    async def async_select_option(self, option: str):
        """Change the selected option."""
        await self.entity_description.select_option(self, option)
        await async_refresh_after_set(self)
