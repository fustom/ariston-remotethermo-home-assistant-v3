"""Support for Ariston sensors."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ARISTON_SELECT_TYPES, AristonSelectEntityDescription
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity, get_coordinator_for_description

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_select: list[AristonSelect] = []

    for description in ARISTON_SELECT_TYPES:
        coordinator = get_coordinator_for_description(hass, entry, description)
        if coordinator is None:
            continue
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
        self.async_write_ha_state()
