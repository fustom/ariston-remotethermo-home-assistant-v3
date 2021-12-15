"""The Ariston integration."""
from __future__ import annotations

import logging

from .ariston import AristonAPI
from .const import DOMAIN, FEATURES, API

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    Platform,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ariston from a config entry."""
    api = AristonAPI()
    reponse = await api.connect(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    if not reponse:
        _LOGGER.error("Failed to connect to Ariston")
        return False

    hass.data.setdefault(DOMAIN, {FEATURES: {}, API: {}})
    device = entry.data[CONF_DEVICE]
    features = await api.get_features_for_device(device["gwId"])
    hass.data[DOMAIN][FEATURES] = features
    hass.data[DOMAIN][API] = api

    if features["hasBoiler"]:
        PLATFORMS.append(Platform.WATER_HEATER)

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
