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
from custom_components.ariston.const import API_URL_SETTING
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
    assert coordinator.last_exception.retry_after == 902  # padded for timer rounding


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

    assert ctx.value.retry_after == 902
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

    assert ctx.value.retry_after == 902


# --- Pinned ariston client behind a fake Ariston cloud ------------


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
        # Older clients sleep out a parsed block once before re-raising.
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
    assert coordinator.last_exception.retry_after == pytest.approx(903, abs=5)
    assert session.requests in (1, 2)  # 0.19.18 retries once, 0.19.21+ does not

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

    assert ctx.value.retry_after == pytest.approx(903, abs=5)
    assert "Traceback" not in caplog.text
    assert session.requests in (1, 2)  # 0.19.18 retries once, 0.19.21+ does not


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

    assert ctx.value.retry_after == 62


async def test_optional_refresh_during_setup_keeps_its_interval(hass):
    """Bus-error/energy refreshes during setup must not adopt a short block."""
    entry = _entry()
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    coordinator = DeviceDataUpdateCoordinator(
        hass,
        SimpleNamespace(name="Test boiler"),
        600,
        "bus_errors",
        AsyncMock(side_effect=_RateLimitException(60)),
        config_entry=entry,
    )

    await coordinator.async_refresh()

    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert coordinator.last_exception.retry_after is None


async def test_setup_retry_waits_out_known_block_without_contacting_ariston(hass):
    """A retry inside a known block (e.g. at HA startup) makes no request."""
    entry = _entry()
    session, patches = _pinned_cloud_patches(b"Requests are blocked for 900 seconds")
    with patches[0], patches[1], pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    requests_after_first_attempt = session.requests

    with patches[0], patches[1], pytest.raises(ConfigEntryNotReady) as ctx:
        await async_setup_entry(hass, entry)

    assert session.requests == requests_after_first_attempt  # nothing sent
    assert ctx.value.retry_after == pytest.approx(900, abs=10)


async def test_first_refresh_block_is_remembered_for_the_next_setup(hass, monkeypatch):
    device = _mock_device()
    device.async_update_state.side_effect = _RateLimitException(900)
    _setup_client(monkeypatch, device)
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    )
    entry = _entry()
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    client_factory = MagicMock()
    monkeypatch.setattr("custom_components.ariston.Ariston", client_factory)
    with pytest.raises(ConfigEntryNotReady) as ctx:
        await async_setup_entry(hass, entry)

    client_factory.assert_not_called()  # no new client, no request
    assert ctx.value.retry_after == pytest.approx(900, abs=10)


async def test_first_refresh_block_without_copied_retry_after(hass, monkeypatch):
    """Home Assistant 2026.10 keeps retry_after on the UpdateFailed cause only."""
    device = _mock_device()
    _setup_client(monkeypatch, device)
    entry = _entry()
    entry.add_to_hass(hass)

    async def first_refresh(self):
        try:
            try:
                raise ConnectionException(429, b"Requests are blocked")
            except ConnectionException as rate_limit:
                raise UpdateFailed("rate limited", retry_after=902) from rate_limit
        except UpdateFailed as update_failed:
            not_ready = ConfigEntryNotReady()  # no retry_after, as on 2026.10
            raise not_ready from update_failed

    monkeypatch.setattr(
        DeviceDataUpdateCoordinator, "async_config_entry_first_refresh", first_refresh
    )
    with pytest.raises(ConfigEntryNotReady) as ctx:
        await async_setup_entry(hass, entry)
    assert ctx.value.retry_after == 902

    client_factory = MagicMock()
    monkeypatch.setattr("custom_components.ariston.Ariston", client_factory)
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    client_factory.assert_not_called()  # the startup retry stays offline


# The pinned client blocks for the parsed duration plus one second, so 299
# gives a block exactly as long as the 300 s polling interval.
@pytest.mark.parametrize("block_seconds", [900, 299])
async def test_first_scheduled_retry_reaches_ariston(hass, freezer, block_seconds):
    """The retry after a block sends a request even if its timer fires early.

    Home Assistant schedules the refresh from the loop time truncated to whole
    seconds, plus 0.05-0.5 s, so it can fire up to 0.95 s before the delay.
    """
    api = AristonAPI("user", "pass")

    async def update():
        return await api._async_get("https://example/menuItems")

    device = SimpleNamespace(name="Test boiler", api=api)
    coordinator = DeviceDataUpdateCoordinator(hass, device, 300, "test", update)
    coordinator.async_add_listener(lambda: None)
    session, patches = _pinned_cloud_patches(
        f"Requests are blocked for {block_seconds} seconds".encode()
    )
    with patches[0], patches[1]:
        await coordinator.async_refresh()
    requests_before = session.requests
    # The reported delay, or the polling interval when none was reported.
    delay = coordinator.last_exception.retry_after or 300

    # Worst case: the timer fires 0.95 s before the scheduled delay.
    freezer.tick(delay - 0.95)
    with patches[0], patches[1]:
        async_fire_time_changed(hass, dt_util.utcnow(), fire_all=True)
        await hass.async_block_till_done()

    assert session.requests == requests_before + 1  # not skipped by the client


@pytest.mark.parametrize(
    "change",
    [
        {CONF_USERNAME: "other@example.com"},
        {API_URL_SETTING: "https://other.example/api/v2/"},
    ],
)
async def test_remembered_block_is_dropped_when_account_or_url_changes(
    hass, monkeypatch, change
):
    """A block on the old account or endpoint does not hold back the new one."""
    entry = _entry()
    entry.add_to_hass(hass)
    session, patches = _pinned_cloud_patches(b"Requests are blocked for 900 seconds")
    with patches[0], patches[1], pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    hass.config_entries.async_update_entry(entry, data={**entry.data, **change})
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    _setup_client(monkeypatch, _mock_device())
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    )
    assert await async_setup_entry(hass, entry)  # contacted Ariston again
