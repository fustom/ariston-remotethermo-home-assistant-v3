"""Tests for HTTP 429 (rate limit) handling in setup and coordinators."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ariston import DeviceAttribute
from ariston.ariston_api import ConnectionException
from ariston.const import SystemType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from pytest_homeassistant.common import MockConfigEntry

from custom_components.ariston import DOMAIN, async_setup_entry
from custom_components.ariston.coordinator import (
    DeviceDataUpdateCoordinator,
    rate_limit_retry_after,
)


def _entry():
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
    )


def _setup_client(monkeypatch, device):
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    monkeypatch.setattr(
        "custom_components.ariston.Ariston", MagicMock(return_value=client)
    )


def _mock_device():
    return SimpleNamespace(
        name="Test boiler",
        gateway="gateway-1",
        has_metering=False,
        system_type=SystemType.BSB,
        async_get_features=AsyncMock(),
        async_update_state=AsyncMock(),
        async_get_bus_errors=AsyncMock(),
    )


class _RateLimitException(ConnectionException):
    """Shape of ariston.ariston_api.RateLimitException (newer library)."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(429, b"Requests are blocked")
        self.retry_after = retry_after


def _coordinator(hass, ariston_device, error: Exception) -> DeviceDataUpdateCoordinator:
    return DeviceDataUpdateCoordinator(
        hass, ariston_device, 300, "test", AsyncMock(side_effect=error)
    )


def test_rate_limit_retry_after_classifies_errors():
    assert rate_limit_retry_after(_RateLimitException(120)) == 120
    # Older library: 429 without a duration.
    assert rate_limit_retry_after(ConnectionException(429, b"blocked")) == 0
    assert rate_limit_retry_after(ConnectionException(500)) is None
    assert rate_limit_retry_after(RuntimeError("boom")) is None


async def test_long_block_delays_next_poll(hass, ariston_device):
    coordinator = _coordinator(hass, ariston_device, _RateLimitException(900))

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert coordinator.last_exception.retry_after == 900


async def test_short_block_never_polls_sooner_than_interval(hass, ariston_device):
    coordinator = _coordinator(hass, ariston_device, _RateLimitException(60))

    await coordinator.async_refresh()

    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert coordinator.last_exception.retry_after is None


async def test_legacy_429_is_reported_as_update_failed(hass, ariston_device, caplog):
    coordinator = _coordinator(
        hass, ariston_device, ConnectionException(429, b"Requests are blocked")
    )

    with caplog.at_level(logging.ERROR):
        await coordinator.async_refresh()

    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert coordinator.last_exception.retry_after is None
    # One concise line, not an "Unexpected error" traceback.
    assert "Unexpected error" not in caplog.text
    assert "rate limiting" in caplog.text


async def test_other_connection_errors_are_untouched(hass, ariston_device):
    error = ConnectionException("Invalid token")
    coordinator = _coordinator(hass, ariston_device, error)

    await coordinator.async_refresh()

    assert coordinator.last_exception is error


async def test_setup_429_raises_not_ready_with_retry_after(hass, monkeypatch, caplog):
    device = _mock_device()
    device.async_get_features.side_effect = _RateLimitException(900)
    _setup_client(monkeypatch, device)
    entry = _entry()

    with caplog.at_level(logging.ERROR), pytest.raises(ConfigEntryNotReady) as ctx:
        await async_setup_entry(hass, entry)

    assert ctx.value.retry_after == 900
    assert "Traceback" not in caplog.text


async def test_first_refresh_429_keeps_retry_after(hass, monkeypatch):
    device = _mock_device()
    device.async_update_state.side_effect = _RateLimitException(900)
    _setup_client(monkeypatch, device)
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    )
    entry = _entry()
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)

    with pytest.raises(ConfigEntryNotReady) as ctx:
        await async_setup_entry(hass, entry)

    assert ctx.value.retry_after == 900
