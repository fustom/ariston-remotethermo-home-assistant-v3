"""Support for Ariston switches."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ARISTON_SWITCH_TYPES, DOMAIN, AristonSwitchEntityDescription
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
    """Set up the Ariston switches from config entry."""
    ariston_switches: list[AristonSwitch] = []
    for description in ARISTON_SWITCH_TYPES:
        coordinator: DeviceDataUpdateCoordinator | None = hass.data[DOMAIN][
            entry.unique_id
        ].get(description.coordinator)
        if is_entity_description_available(coordinator, description):
            ariston_switches.append(
                AristonSwitch(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_switches)


class AristonSwitch(AristonEntity, SwitchEntity):
    """Base class for specific ariston switches."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description)

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.entity_description.get_is_on(self)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self.entity_description.set_value(self, True)
        await async_refresh_after_set(self)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        await self.entity_description.set_value(self, False)
        await async_refresh_after_set(self)
