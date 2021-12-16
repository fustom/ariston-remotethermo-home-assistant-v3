"""The Ariston integration."""
from __future__ import annotations
from datetime import timedelta

import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .ariston import AristonAPI
from .const import COORDINATORS, DOMAIN, FEATURES, API

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
    reponse = await api.async_connect(
        entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    if not reponse:
        _LOGGER.error("Failed to connect to Ariston")
        return False

    device = entry.data[CONF_DEVICE]
    features = await api.async_get_features_for_device(device["gwId"])

    async def async_update_data():
        return await api.async_get_device_properies(
            device["gwId"], 1, features, "en-US"
        )

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        # Name of the data. For logging purposes.
        name="sensor",
        update_method=async_update_data,
        # Polling interval. Will only be polled if there are subscribers.
        update_interval=timedelta(seconds=60),
    )

    hass.data.setdefault(DOMAIN, {FEATURES: {}, API: {}, COORDINATORS: {}})
    hass.data[DOMAIN][FEATURES] = features
    hass.data[DOMAIN][API] = api
    hass.data[DOMAIN][COORDINATORS] = coordinator

    # if features["hasBoiler"]:
    #     PLATFORMS.append(Platform.WATER_HEATER)

    await coordinator.async_config_entry_first_refresh()

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if hass.data[DOMAIN].get(API) is not None:
        hass.data[DOMAIN].pop(API, None)

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
