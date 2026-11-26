"""The Ariston integration."""

from __future__ import annotations

import logging
import time

import voluptuous as vol

from ariston import Ariston, DeviceAttribute, SystemType
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT
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
    RATED_POWER_W,
)
from .coordinator import (
    DeviceDataUpdateCoordinator,
    pad_block_delay,
    rate_limit_retry_after,
)

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


# Per config entry: when an Ariston 429 block seen during setup ends. Kept
# outside the entry's runtime data so it survives failed setup attempts, which
# each create a fresh client that knows nothing about the block.
RATE_LIMIT_UNTIL = f"{DOMAIN}_rate_limit_until"


def _rate_limited(retry_after: float | None) -> ConfigEntryNotReady:
    """Build the ConfigEntryNotReady for an Ariston 429 block."""
    not_ready = ConfigEntryNotReady("Ariston cloud is rate limiting requests (HTTP 429)")
    # Set as an attribute: the retry_after keyword only exists on Home
    # Assistant 2026.11+, older versions ignore the attribute.
    not_ready.retry_after = pad_block_delay(retry_after) if retry_after else None
    return not_ready


def _reported_delay(error: BaseException) -> float | None:
    """Return the first retry_after set on error or its cause chain.

    Home Assistant 2026.11+ copies the coordinator's retry_after onto the
    ConfigEntryNotReady of a failed first refresh; 2026.10 leaves it on the
    UpdateFailed cause only.
    """
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if (retry_after := getattr(error, "retry_after", None)) is not None:
            return retry_after
        error = error.__cause__
    return None


def _remember_block(hass: HomeAssistant, entry: ConfigEntry, retry_after: float | None) -> None:
    """Remember a known block so the next setup attempt waits it out."""
    if retry_after:
        hass.data.setdefault(RATE_LIMIT_UNTIL, {})[entry.entry_id] = (
            time.time() + retry_after
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ariston from a config entry."""
    # Home Assistant also retries setup when it finishes starting, whatever
    # retry_after said: do not contact Ariston while a known block lasts.
    blocked_until = hass.data.get(RATE_LIMIT_UNTIL, {}).get(entry.entry_id, 0.0)
    if (remaining := blocked_until - time.time()) > 0:
        raise _rate_limited(remaining)

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

        scan_interval_seconds = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
        )
        coordinator = DeviceDataUpdateCoordinator(
            hass,
            device,
            scan_interval_seconds,
            COORDINATOR,
            device.async_update_state,
            config_entry=entry,
        )

        hass.data.setdefault(DOMAIN, {}).setdefault(
            entry.unique_id, {COORDINATOR: {}, ENERGY_COORDINATOR: {}}
        )
        coordinator.rated_power_w = entry.options.get(RATED_POWER_W)
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
            await energy_coordinator.async_refresh()

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
    except ConfigEntryNotReady as error:
        # A 429 on the first refresh: remember the block, taking its delay
        # from the coordinator or, failing that, from the client's deadline.
        api = getattr(ariston, "api", None)
        if (retry_after := rate_limit_retry_after(error, api)) is not None:
            retry_after = _reported_delay(error) or retry_after
            _remember_block(hass, entry, retry_after)
            # Already padded by the coordinator when it came from there.
            error.retry_after = retry_after or None
        raise
    except Exception as error:
        api = getattr(ariston, "api", None)
        if (retry_after := rate_limit_retry_after(error, api)) is not None:
            # Expected while the cloud blocks the account: no traceback, and
            # let the setup retry wait out the block window.
            _remember_block(hass, entry, retry_after)
            raise _rate_limited(retry_after) from error
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
