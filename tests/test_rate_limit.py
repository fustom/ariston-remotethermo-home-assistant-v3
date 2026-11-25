"""Tests for HTTP 429 (rate limit) handling in setup and coordinators."""

from datetime import timedelta
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ariston import DeviceAttribute
from ariston.ariston_api import AristonAPI, ConnectionException
from ariston.const import SystemType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

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


# --- Pinned client (ariston==0.19.18) behind a fake Ariston cloud ------------


class _FakeContent:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _FakeResponse:
    def __init__(self, status: int, payload: bytes = b"") -> None:
        self.status = status
        self.ok = status < 400
        self.headers = {}
        self.content = _FakeContent(payload)
        self.content_length = len(payload)


def _blocked_cloud(body: bytes):
    """aiohttp.ClientSession stand-in that answers every request with a 429."""

    class _Session:
        requests = 0

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def request(self, *args, **kwargs):
            type(self).requests += 1
            return _FakeResponse(429, body)

    return _Session


def _pinned_cloud_patches(body: bytes):
    session = _blocked_cloud(body)
    return session, (
        patch("ariston.ariston_api.aiohttp.ClientSession", session),
        # The client sleeps out a parsed block once before re-raising.
        patch("ariston.ariston_api.asyncio.sleep", AsyncMock()),
    )


def test_wrapped_login_429_is_found_in_the_cause_chain():
    try:
        try:
            raise ConnectionException(429, b"Requests are blocked")
        except ConnectionException as inner:
            raise ConnectionException() from inner
    except ConnectionException as wrapped:
        assert rate_limit_retry_after(wrapped) == 0


async def test_pinned_client_block_duration_schedules_next_poll(hass):
    """A 900 s block from the pinned client delays the next poll past 300 s."""
    api = AristonAPI("user", "pass")
    calls = []

    async def update():
        calls.append(1)
        return await api._async_get("https://example/menuItems")

    device = SimpleNamespace(name="Test boiler", api=api)
    coordinator = DeviceDataUpdateCoordinator(hass, device, 300, "test", update)
    coordinator.async_add_listener(lambda: None)
    session, patches = _pinned_cloud_patches(b"Requests are blocked for 900 seconds")
    with patches[0], patches[1]:
        await coordinator.async_refresh()

    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert coordinator.last_exception.retry_after == pytest.approx(901, abs=5)
    assert session.requests == 2  # first request + the client's one retry

    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=310))
    await hass.async_block_till_done()
    assert len(calls) == 1  # the normal 300 s poll did not run

    with patches[0], patches[1]:
        async_fire_time_changed(hass, now + timedelta(seconds=910))
        await hass.async_block_till_done()
    assert len(calls) == 2  # polled again once the block was over


async def test_pinned_client_login_429_raises_not_ready(hass, caplog):
    """A 429 on login (wrapped by the client) defers setup by the block."""
    entry = _entry()
    session, patches = _pinned_cloud_patches(b"Requests are blocked for 900 seconds")
    with patches[0], patches[1], caplog.at_level(logging.ERROR), pytest.raises(
        ConfigEntryNotReady
    ) as ctx:
        await async_setup_entry(hass, entry)

    assert ctx.value.retry_after == pytest.approx(901, abs=5)
    assert "Traceback" not in caplog.text
    assert session.requests == 2


async def test_first_refresh_passes_short_block_through(hass, monkeypatch):
    """During setup a 60 s block is passed on, though shorter than polling."""
    device = _mock_device()
    device.async_update_state.side_effect = _RateLimitException(60)
    _setup_client(monkeypatch, device)
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    )
    entry = _entry()
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)

    with pytest.raises(ConfigEntryNotReady) as ctx:
        await async_setup_entry(hass, entry)

    assert ctx.value.retry_after == 60
