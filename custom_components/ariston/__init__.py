"""The Ariston integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from ariston import Ariston, DeviceAttribute, SystemType
from ariston.const import (
    ARISTON_API_URL,
    ARISTON_DATA_ITEMS,
    ARISTON_REMOTE,
    ARISTON_USER_AGENT,
    DeviceFeatures,
    PropertyType,
    ThermostatProperties,
    ZoneAttribute,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_COORDINATOR,
    BUS_ERRORS_SCAN_INTERVAL,
    COORDINATOR,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
    get_flow_fallback_zones,
)
from .coordinator import DeviceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
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
        vol.Required(ATTR_ZONE): vol.All(cv.positive_int, vol.Range(min=1)),
        vol.Required(ATTR_VALUE): vol.Coerce(float),
    }
)


async def _async_poll_fallback_flow_properties(
    device: Any,
    api_url: str,
) -> None:
    """Fetch only the optional flow controls for earlier inferred zones."""
    fallback_zones = get_flow_fallback_zones(
        [
            zone[ZoneAttribute.NUM]
            for zone in device.features.get(DeviceFeatures.ZONES, [])
        ]
    )
    if not fallback_zones:
        return

    items = [
        {"id": property_id.value, "zn": zone_number}
        for property_id in (
            ThermostatProperties.HEATING_FLOW_TEMP,
            ThermostatProperties.HEATING_FLOW_OFFSET,
        )
        for zone_number in fallback_zones
    ]
    features = {
        DeviceFeatures.ZONES: [
            {ZoneAttribute.NUM: zone_number} for zone_number in fallback_zones
        ]
    }
    path = (
        f"{api_url}{ARISTON_REMOTE}/{ARISTON_DATA_ITEMS}/"
        f"{device.gw}/get?umsys={device.umsys}"
    )
    properties = await device.api._async_request_properties(
        path, items, features, device.language_tag, False
    )

    if not isinstance(properties, dict) or not isinstance(
        properties.get("items"), list
    ):
        return

    data_items = device.data.get("items")
    if not isinstance(data_items, list):
        return

    requested_items = {(item["id"], item["zn"]) for item in items}
    existing_items = {
        (item.get("id"), item.get(PropertyType.ZONE)): item
        for item in data_items
    }
    for item in properties["items"]:
        identity = (item.get("id"), item.get(PropertyType.ZONE))
        if identity not in requested_items:
            continue
        if identity in existing_items:
            existing_items[identity].update(item)
        else:
            data_items.append(item)
            existing_items[identity] = item


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ariston from a config entry."""
    ariston = Ariston()
    try:
        api_url_setting = entry.data.get(API_URL_SETTING, ARISTON_API_URL)

        api_user_agent = entry.data.get(API_USER_AGENT, ARISTON_USER_AGENT)

        reponse = await ariston.async_connect(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            api_url_setting,
            api_user_agent,
        )
        if not reponse:
            _LOGGER.error(
                "Failed to connect to Ariston with device: %s",
                entry.data[CONF_DEVICE].get(DeviceAttribute.NAME),
            )
            raise ConfigEntryAuthFailed

        device = await ariston.async_hello(
            entry.data[CONF_DEVICE].get(DeviceAttribute.GW),
            hass.config.units is METRIC_SYSTEM,
        )
        if device is None:
            return False

        await device.async_get_features()

        async def async_update_state() -> None:
            """Update the device normally, then best-effort poll inferred zones."""
            await device.async_update_state()
            if device.system_type == SystemType.GALEVO:
                try:
                    await _async_poll_fallback_flow_properties(
                        device, api_url_setting
                    )
                except Exception:
                    _LOGGER.warning(
                        "Unable to update optional fallback flow properties",
                        exc_info=True,
                    )

        scan_interval_seconds = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
        )
        coordinator = DeviceDataUpdateCoordinator(
            hass,
            device,
            scan_interval_seconds,
            COORDINATOR,
            async_update_state,
            config_entry=entry,
        )

        hass.data.setdefault(DOMAIN, {}).setdefault(
            entry.unique_id, {COORDINATOR: {}, ENERGY_COORDINATOR: {}}
        )
        hass.data[DOMAIN][entry.unique_id][COORDINATOR] = coordinator

        await coordinator.async_config_entry_first_refresh()

        bus_errors_scan_interval_seconds = entry.options.get(
            BUS_ERRORS_SCAN_INTERVAL, DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS
        )
        bus_errors_coordinator = DeviceDataUpdateCoordinator(
            hass,
            device,
            bus_errors_scan_interval_seconds,
            BUS_ERRORS_COORDINATOR,
            device.async_get_bus_errors,
            config_entry=entry,
        )
        hass.data[DOMAIN][entry.unique_id][BUS_ERRORS_COORDINATOR] = (
            bus_errors_coordinator
        )
        await bus_errors_coordinator.async_refresh()

        if device.has_metering:
            energy_interval_minutes = entry.options.get(
                ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
            )
            energy_coordinator = DeviceDataUpdateCoordinator(
                hass,
                device,
                energy_interval_minutes * 60,
                ENERGY_COORDINATOR,
                device.async_update_energy,
                config_entry=entry,
            )
            hass.data[DOMAIN][entry.unique_id][ENERGY_COORDINATOR] = energy_coordinator
            await energy_coordinator.async_config_entry_first_refresh()

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        entry.async_on_unload(entry.add_update_listener(update_listener))

        if device.system_type == SystemType.GALEVO:

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
    except ConfigEntryAuthFailed:
        raise
    except Exception as error:
        _LOGGER.exception("")
        raise ConfigEntryNotReady from error

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
