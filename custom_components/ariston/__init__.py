"""The Ariston integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from .ariston import (
    AristonAPI,
    DeviceAttribute,
    DeviceFeatures,
    SystemType,
    VelisDeviceAttribute,
    WheType,
)
from .coordinator import DeviceDataUpdateCoordinator
from .const import (
    COORDINATOR,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_EXTRA_ENERGY_FEATURES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
    EXTRA_ENERGY_FEATURES,
)
from .galevo_device import AristonGalevoDevice
from .evo_device import AristonEvoDevice
from .lydos_hybrid_device import AristonLydosHybridDevice

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.config_entries import ConfigEntry
from homeassistant.util.unit_system import METRIC_SYSTEM
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    Platform,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE,
)
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.WATER_HEATER,
]

SERVICE_SET_ITEM_BY_ID = "set_item_by_id"
ATTR_ITEM_ID = "item_id"
ATTR_ZONE = "zone"
ATTR_VALUE = "value"

SET_ITEM_BY_ID_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_ITEM_ID): cv.string,
        vol.Required(ATTR_ZONE): cv.positive_int,
        vol.Required(ATTR_VALUE): vol.Coerce(float),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ariston from a config entry."""
    api = AristonAPI(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    try:
        reponse = await api.async_connect()
        if not reponse:
            _LOGGER.error(
                "Failed to connect to Ariston with device: %s",
                entry.data[CONF_DEVICE].get(DeviceAttribute.NAME),
            )
            raise ConfigEntryAuthFailed()
    except Exception as error:
        _LOGGER.exception("")
        raise ConfigEntryNotReady() from error

    extra_energy_features = entry.options.get(
        EXTRA_ENERGY_FEATURES, DEFAULT_EXTRA_ENERGY_FEATURES
    )

    if entry.data[CONF_DEVICE].get(DeviceAttribute.SYS) == SystemType.GALEVO:
        device = AristonGalevoDevice(
            entry.data[CONF_DEVICE],
            api,
            extra_energy_features,
            hass.config.units is METRIC_SYSTEM,
        )
    elif entry.data[CONF_DEVICE].get(DeviceAttribute.SYS) == SystemType.VELIS:
        if (
            entry.data[CONF_DEVICE].get(VelisDeviceAttribute.WHE_TYPE)
            == WheType.LydosHybrid
        ):
            device = AristonLydosHybridDevice(
                entry.data[CONF_DEVICE],
                api,
                extra_energy_features,
                hass.config.units is METRIC_SYSTEM,
            )
        elif entry.data[CONF_DEVICE].get(VelisDeviceAttribute.WHE_TYPE) == WheType.Evo:
            device = AristonEvoDevice(
                entry.data[CONF_DEVICE],
                api,
                extra_energy_features,
                hass.config.units is METRIC_SYSTEM,
            )
        else:
            # Fallback to Evo
            device = AristonEvoDevice(
                entry.data[CONF_DEVICE],
                api,
                extra_energy_features,
                hass.config.units is METRIC_SYSTEM,
            )
            _LOGGER.error(
                "Your device (%s) is currently not supported. Contact with the developer. Your fallback device is Velis Evo maybe working",
                entry.data[CONF_DEVICE].get(VelisDeviceAttribute.WHE_TYPE),
            )

            # _LOGGER.error(
            #     "Your velis device (%s) is currently not supported. Contact with the developer",
            #     entry.data[CONF_DEVICE].get(VelisDeviceAttribute.WHE_TYPE),
            # )
            # return False
    else:
        _LOGGER.error(
            "Your device (%s) is currently not supported. Contact with the developer",
            entry.data[CONF_DEVICE].get(DeviceAttribute.SYS),
        )
        return False

    await device.async_get_features()

    scan_interval_seconds = entry.options.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
    )
    coordinator = DeviceDataUpdateCoordinator(
        hass, device, scan_interval_seconds, COORDINATOR, device.async_update_state
    )

    hass.data.setdefault(DOMAIN, {}).setdefault(
        entry.unique_id, {COORDINATOR: {}, ENERGY_COORDINATOR: {}}
    )
    hass.data[DOMAIN][entry.unique_id][COORDINATOR] = coordinator

    await coordinator.async_config_entry_first_refresh()

    if device.features.get(DeviceFeatures.HAS_METERING):
        energy_interval_minutes = entry.options.get(
            ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
        )
        energy_coordinator = DeviceDataUpdateCoordinator(
            hass,
            device,
            energy_interval_minutes * 60,
            ENERGY_COORDINATOR,
            device.async_update_energy,
        )
        hass.data[DOMAIN][entry.unique_id][ENERGY_COORDINATOR] = energy_coordinator
        await energy_coordinator.async_config_entry_first_refresh()

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    if device.attributes.get(DeviceAttribute.SYS) == SystemType.GALEVO:

        async def async_set_item_by_id_service(service_call):
            """Create a vacation on the target device."""
            device_id = service_call.data.get(ATTR_DEVICE_ID)
            item_id = service_call.data.get(ATTR_ITEM_ID)
            zone = service_call.data.get(ATTR_ZONE)
            value = service_call.data.get(ATTR_VALUE)

            device_registry = dr.async_get(hass)
            device = device_registry.devices[device_id]

            entry = hass.config_entries.async_get_entry(
                next(iter(device.config_entries))
            )
            coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][
                entry.unique_id
            ][COORDINATOR]
            await coordinator.device.async_set_item_by_id(item_id, value, zone)

        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_ITEM_BY_ID,
            async_set_item_by_id_service,
            schema=SET_ITEM_BY_ID_SCHEMA,
        )

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.unique_id)

    return unload_ok
