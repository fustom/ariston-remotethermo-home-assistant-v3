"""Support for Ariston switches."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.switch import SwitchEntity

from .entity import AristonEntity
from .const import ARISTON_SWITCH_TYPES, DOMAIN, AristonSwitchEntityDescription
from .coordinator import DeviceDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston switches from config entry."""
    ariston_switches: list[AristonSwitch] = []
    for description in ARISTON_SWITCH_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]
        if coordinator.device.are_device_features_available(
            description.device_features, description.system_types, description.whe_types
        ):
            ariston_switches.append(
                AristonSwitch(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_switches)


class AristonSwitch(AristonEntity, SwitchEntity):
    """Base class for specific ariston switches"""

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
        return getattr(self.device, self.entity_description.getter.__name__)()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await getattr(self.device, self.entity_description.setter.__name__)(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        await getattr(self.device, self.entity_description.setter.__name__)(False)
        self.async_write_ha_state()
