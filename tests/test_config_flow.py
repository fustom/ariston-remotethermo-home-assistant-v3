"""Tests for Ariston account and options flows."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ariston import DeviceAttribute
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType, SOURCE_REAUTH, SOURCE_USER
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ariston import config_flow
from custom_components.ariston.const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_SCAN_INTERVAL,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENERGY_SCAN_INTERVAL,
)


@pytest.fixture
def ariston_client(monkeypatch):
    """Replace the cloud client with an async mock."""
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_discover = AsyncMock(return_value=[])
    monkeypatch.setattr(config_flow, "Ariston", MagicMock(return_value=client))
    return client


def _input(**overrides):
    data = {
        CONF_USERNAME: "user@example.com",
        CONF_PASSWORD: "secret",
        API_URL_SETTING: ARISTON_API_URL,
        API_USER_AGENT: ARISTON_USER_AGENT,
    }
    return data | overrides


def _device(gateway, name, serial):
    return {
        DeviceAttribute.GW: gateway,
        DeviceAttribute.NAME: name,
        DeviceAttribute.SN: serial,
    }


async def _start_user_flow(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )


async def test_user_step_shows_credential_form(hass):
    result = await _start_user_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_reports_invalid_auth(hass, ariston_client):
    ariston_client.async_connect.return_value = False
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input()
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    ariston_client.async_discover.assert_not_awaited()


async def test_user_step_reports_unexpected_connection_error(
    hass, ariston_client
):
    ariston_client.async_connect.side_effect = RuntimeError("cloud unavailable")
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input()
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_step_reports_when_no_devices_are_found(hass, ariston_client):
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input()
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "no device found"}


async def test_single_device_creates_config_entry(hass, ariston_client):
    device = _device("gateway-1", "Boiler", "serial-1")
    ariston_client.async_discover.return_value = [device]
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input()
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Boiler"
    assert result["data"][CONF_USERNAME] == "user@example.com"
    assert result["data"][CONF_PASSWORD] == "secret"
    assert result["data"][CONF_DEVICE] == device


async def test_multiple_devices_require_a_selection(hass, ariston_client):
    first = _device("gateway-1", "Boiler", "serial-1")
    second = _device("gateway-2", "Water heater", "serial-2")
    ariston_client.async_discover.return_value = [first, second]
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input()
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"select_device": "Water heater - serial-2"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Water heater"
    assert result["data"][CONF_DEVICE] == second


async def test_reauth_updates_existing_entry_and_reloads(hass, monkeypatch, ariston_client):
    device = _device("gateway-1", "Boiler", "serial-1")
    ariston_client.async_discover.return_value = [device]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="gateway-1",
        data={CONF_USERNAME: "old-user", CONF_PASSWORD: "old-password"},
    )
    entry.add_to_hass(hass)

    async def return_existing_entry(flow, unique_id, *, raise_on_progress=True):
        assert unique_id == "gateway-1"
        return entry

    monkeypatch.setattr(
        config_flow.AristonConfigFlow,
        "async_set_unique_id",
        return_existing_entry,
    )
    reload_entry = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_reload", reload_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input()
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_USERNAME] == "user@example.com"
    assert entry.data[CONF_DEVICE] == device
    reload_entry.assert_awaited_once_with(entry.entry_id)


async def test_options_flow_uses_defaults_and_saves_values(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="gateway-1", data={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"]({}) == {
        "scan_interval": DEFAULT_SCAN_INTERVAL_SECONDS,
        ENERGY_SCAN_INTERVAL: DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
        BUS_ERRORS_SCAN_INTERVAL: DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    }

    options = {
        "scan_interval": 120,
        ENERGY_SCAN_INTERVAL: 30,
        BUS_ERRORS_SCAN_INTERVAL: 900,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == options


@pytest.mark.parametrize(
    ("stored_options", "expected"),
    [
        ({}, (180, 60, 600)),
        (
            {"scan_interval": 90, ENERGY_SCAN_INTERVAL: 15, BUS_ERRORS_SCAN_INTERVAL: 240},
            (90, 15, 240),
        ),
    ],
)
async def test_options_flow_shows_stored_values(
    hass, stored_options, expected
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="gateway-1",
        data={},
        options=stored_options,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    values = result["data_schema"]({})

    assert expected == (
        values["scan_interval"],
        values[ENERGY_SCAN_INTERVAL],
        values[BUS_ERRORS_SCAN_INTERVAL],
    )
