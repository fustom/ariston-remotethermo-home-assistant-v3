"""Tests for config-entry setup, services, and unload handling."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

from ariston import DeviceAttribute
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT, SystemType
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.util.unit_system import METRIC_SYSTEM
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ariston import (
    ATTR_ITEM_ID,
    ATTR_VALUE,
    ATTR_ZONE,
    DOMAIN,
    SERVICE_SET_ITEM_BY_ID,
    SET_ITEM_BY_ID_SCHEMA,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.ariston.const import (
    BUS_ERRORS_COORDINATOR,
    BUS_ERRORS_SCAN_INTERVAL,
    COORDINATOR,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
)


def _entry(**options):
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="gateway-1",
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_DEVICE: {
                DeviceAttribute.GW: "gateway-1",
                DeviceAttribute.NAME: "Test boiler",
            },
        },
        options=options,
    )


def _mock_client(monkeypatch, client):
    monkeypatch.setattr(
        "custom_components.ariston.Ariston", MagicMock(return_value=client)
    )


def _mock_device(*, has_metering=False, system_type=SystemType.BSB):
    return SimpleNamespace(
        name="Test boiler",
        gateway="gateway-1",
        has_metering=has_metering,
        system_type=system_type,
        async_get_features=AsyncMock(),
        async_update_state=AsyncMock(),
        async_get_bus_errors=AsyncMock(),
        async_update_energy=AsyncMock(),
        async_set_item_by_id=AsyncMock(),
        async_set_holiday=AsyncMock(),
    )


async def test_setup_creates_coordinators_and_unload_removes_entry_data(
    hass, monkeypatch
):
    device = _mock_device(has_metering=True, system_type=SystemType.GALEVO)
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    forward_platforms = AsyncMock()
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", forward_platforms
    )
    entry = _entry(
        **{
            "scan_interval": 120,
            ENERGY_SCAN_INTERVAL: 30,
            BUS_ERRORS_SCAN_INTERVAL: 900,
        }
    )
    entry.add_to_hass(hass)
    entry.state = ConfigEntryState.SETUP_IN_PROGRESS

    assert await async_setup_entry(hass, entry)

    coordinators = hass.data[DOMAIN][entry.unique_id]
    assert set(coordinators) == {COORDINATOR, BUS_ERRORS_COORDINATOR, ENERGY_COORDINATOR}
    assert coordinators[COORDINATOR].update_interval.total_seconds() == 120
    assert coordinators[BUS_ERRORS_COORDINATOR].update_interval.total_seconds() == 900
    assert coordinators[ENERGY_COORDINATOR].update_interval.total_seconds() == 1800
    client.async_connect.assert_awaited_once_with(
        "user@example.com", "secret", ARISTON_API_URL, ARISTON_USER_AGENT
    )
    client.async_hello.assert_awaited_once_with(
        "gateway-1", hass.config.units is METRIC_SYSTEM
    )
    device.async_get_features.assert_awaited_once()
    device.async_update_state.assert_awaited_once()
    device.async_get_bus_errors.assert_awaited_once()
    device.async_update_energy.assert_awaited_once()
    forward_platforms.assert_awaited_once()
    assert hass.services.has_service(DOMAIN, SERVICE_SET_ITEM_BY_ID)

    registered_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "serial-1")},
        name="Test boiler",
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_ITEM_BY_ID,
        {
            ATTR_DEVICE_ID: registered_device.id,
            ATTR_ITEM_ID: "comfort_temp",
            ATTR_ZONE: 1,
            ATTR_VALUE: 20,
        },
        blocking=True,
    )
    device.async_set_item_by_id.assert_awaited_once_with(
        "comfort_temp", 20.0, 1
    )

    unload_platforms = AsyncMock(return_value=True)
    monkeypatch.setattr(
        hass.config_entries, "async_unload_platforms", unload_platforms
    )
    assert await async_unload_entry(hass, entry)
    assert entry.unique_id not in hass.data[DOMAIN]


async def test_setup_skips_energy_coordinator_when_device_has_no_metering(
    hass, monkeypatch
):
    device = _mock_device(has_metering=False)
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    )
    entry = _entry()
    entry.add_to_hass(hass)
    entry.state = ConfigEntryState.SETUP_IN_PROGRESS

    assert await async_setup_entry(hass, entry)

    coordinators = hass.data[DOMAIN][entry.unique_id]
    assert set(coordinators) == {
        COORDINATOR,
        BUS_ERRORS_COORDINATOR,
        ENERGY_COORDINATOR,
    }
    assert coordinators[ENERGY_COORDINATOR] == {}
    assert coordinators[COORDINATOR].update_interval.total_seconds() == (
        DEFAULT_SCAN_INTERVAL_SECONDS
    )
    assert coordinators[BUS_ERRORS_COORDINATOR].update_interval.total_seconds() == (
        DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS
    )
    assert not hass.services.has_service(DOMAIN, SERVICE_SET_ITEM_BY_ID)


async def test_setup_raises_auth_error_when_cloud_rejects_credentials(
    hass, monkeypatch
):
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=False)
    _mock_client(monkeypatch, client)
    entry = _entry()

    with pytest.raises(ConfigEntryAuthFailed):
        await async_setup_entry(hass, entry)


async def test_setup_wraps_unexpected_cloud_error_as_not_ready(hass, monkeypatch):
    client = MagicMock()
    client.async_connect = AsyncMock(side_effect=RuntimeError("cloud unavailable"))
    _mock_client(monkeypatch, client)
    entry = _entry()

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)


async def test_setup_returns_false_when_device_is_not_found(hass, monkeypatch):
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=None)
    _mock_client(monkeypatch, client)

    assert await async_setup_entry(hass, _entry()) is False
    client.async_hello.assert_awaited_once()


def test_set_item_by_id_schema_accepts_valid_payload():
    payload = {
        ATTR_DEVICE_ID: "device-1",
        ATTR_ITEM_ID: "comfort_temp",
        ATTR_ZONE: 1,
        ATTR_VALUE: 20,
    }

    validated = SET_ITEM_BY_ID_SCHEMA(payload)

    assert validated[ATTR_VALUE] == 20.0
    assert isinstance(validated[ATTR_VALUE], float)


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {ATTR_DEVICE_ID: "device-1", ATTR_ITEM_ID: "item", ATTR_ZONE: 0, ATTR_VALUE: 1},
        {ATTR_DEVICE_ID: "device-1", ATTR_ITEM_ID: "item", ATTR_ZONE: 1},
    ],
)
def test_set_item_by_id_schema_rejects_invalid_payload(invalid_payload):
    with pytest.raises(vol.Invalid):
        SET_ITEM_BY_ID_SCHEMA(invalid_payload)


async def test_unload_keeps_entry_data_when_platform_unload_fails(hass, monkeypatch):
    entry = _entry()
    hass.data[DOMAIN] = {entry.unique_id: {COORDINATOR: object()}}
    monkeypatch.setattr(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    )

    assert await async_unload_entry(hass, entry) is False
    assert entry.unique_id in hass.data[DOMAIN]
