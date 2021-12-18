"""The Ariston integration."""
from __future__ import annotations

import logging

from .ariston import AristonAPI
from .coordinator import DeviceDataUpdateCoordinator
from .const import DOMAIN
from .device import AristonDevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    Platform,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ariston from a config entry."""
    api = AristonAPI()
    reponse = await api.async_connect(
        entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    if not reponse:
        _LOGGER.error("Failed to connect to Ariston")
        return False

    device = AristonDevice(entry.data[CONF_DEVICE], api)
    await device.async_get_features()

    coordinator = DeviceDataUpdateCoordinator(hass, device)

    hass.data.setdefault(DOMAIN, {entry.unique_id: {}})
    hass.data[DOMAIN][entry.unique_id] = coordinator

    if device.features.has_boiler:
        PLATFORMS.append(Platform.WATER_HEATER)

    await coordinator.async_config_entry_first_refresh()

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.unique_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
