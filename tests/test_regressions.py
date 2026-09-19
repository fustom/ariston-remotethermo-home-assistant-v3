"""Regression tests for Ariston integration behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import homeassistant  # noqa: F401  # Install Home Assistant's schema compatibility
import pytest
from ariston import ConnectionException, DeviceAttribute
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ariston import _async_first_refresh_optional
from custom_components.ariston.config_flow import AristonConfigFlow
from custom_components.ariston.coordinator import DeviceDataUpdateCoordinator


def test_device_selection_uses_unique_gateway() -> None:
    """Select the requested device when display names are duplicated."""
    first_device = {
        DeviceAttribute.GW: "gateway-1",
        DeviceAttribute.NAME: "Boiler",
        DeviceAttribute.SN: "Model",
    }
    second_device = {
        DeviceAttribute.GW: "gateway-2",
        DeviceAttribute.NAME: "Boiler",
        DeviceAttribute.SN: "Model",
    }
    flow = AristonConfigFlow()
    flow.cloud_devices = {
        "gateway-1": first_device,
        "gateway-2": second_device,
    }
    selected_devices = []
    expected_result = {"type": "selected"}

    async def capture_selection(device):
        selected_devices.append(device)
        return expected_result

    flow.async_create_or_update_entry = capture_selection

    form = asyncio.run(flow.async_step_select())
    assert form["step_id"] == "select"
    assert form["data_schema"]({"select_device": "gateway-2"}) == {
        "select_device": "gateway-2"
    }

    result = asyncio.run(flow.async_step_select({"select_device": "gateway-2"}))

    assert result is expected_result
    assert selected_devices == [second_device]


def test_connection_error_is_returned_without_internal_retry() -> None:
    """Return a recoverable error immediately so Home Assistant schedules retries."""
    attempts = 0

    async def failing_update():
        nonlocal attempts
        attempts += 1
        raise ConnectionException("offline")

    coordinator = DeviceDataUpdateCoordinator(
        object(),
        None,
        SimpleNamespace(name="Boiler"),
        180,
        "state",
        failing_update,
    )

    async def run_update() -> None:
        with pytest.raises(UpdateFailed, match="offline"):
            await asyncio.wait_for(coordinator._async_update_data(), timeout=0.1)

    asyncio.run(run_update())

    assert attempts == 1


def test_optional_first_refresh_suppresses_retryable_not_ready() -> None:
    """Allow optional connection failures to recover through scheduled refreshes."""
    not_ready = ConfigEntryNotReady()
    not_ready.__cause__ = UpdateFailed("offline")
    coordinator = SimpleNamespace(
        async_config_entry_first_refresh=AsyncMock(side_effect=not_ready)
    )

    asyncio.run(_async_first_refresh_optional(coordinator, "energy"))

    coordinator.async_config_entry_first_refresh.assert_awaited_once()


def test_optional_first_refresh_propagates_wrapped_programming_error() -> None:
    """Do not treat Home Assistant's wrapper around programming errors as offline."""
    not_ready = ConfigEntryNotReady()
    not_ready.__cause__ = RuntimeError("broken")
    coordinator = SimpleNamespace(
        async_config_entry_first_refresh=AsyncMock(side_effect=not_ready)
    )

    with pytest.raises(ConfigEntryNotReady) as raised:
        asyncio.run(_async_first_refresh_optional(coordinator, "energy"))

    assert isinstance(raised.value.__cause__, RuntimeError)


def test_optional_first_refresh_propagates_unexpected_error() -> None:
    """Do not hide programming errors during optional setup."""
    coordinator = SimpleNamespace(
        async_config_entry_first_refresh=AsyncMock(side_effect=RuntimeError("broken"))
    )

    with pytest.raises(RuntimeError, match="broken"):
        asyncio.run(_async_first_refresh_optional(coordinator, "energy"))


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ConnectionException("offline"), None),
        (RuntimeError("broken"), ConfigEntryNotReady),
        (ConfigEntryAuthFailed("bad credentials"), ConfigEntryAuthFailed),
    ],
)
def test_optional_first_refresh_uses_real_coordinator_error_handling(
    error, expected
) -> None:
    """Exercise Home Assistant's real first-refresh wrapping and auth behavior."""

    async def failing_update():
        raise error

    entry = SimpleNamespace(
        state=ConfigEntryState.SETUP_IN_PROGRESS,
        async_on_unload=lambda callback: None,
    )
    coordinator = DeviceDataUpdateCoordinator(
        SimpleNamespace(is_stopping=False),
        entry,
        SimpleNamespace(name="Boiler"),
        180,
        "energy",
        failing_update,
    )

    if expected is None:
        asyncio.run(_async_first_refresh_optional(coordinator, "energy"))
    else:
        with pytest.raises(expected):
            asyncio.run(_async_first_refresh_optional(coordinator, "energy"))


def test_coordinator_can_recover_on_a_later_scheduled_attempt() -> None:
    """Keep coordinator attempts independent so a later poll can recover."""
    attempts = 0

    async def update():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionException("offline")
        return {"online": True}

    coordinator = DeviceDataUpdateCoordinator(
        object(),
        None,
        SimpleNamespace(name="Boiler"),
        180,
        "state",
        update,
    )

    with pytest.raises(UpdateFailed):
        asyncio.run(coordinator._async_update_data())

    assert asyncio.run(coordinator._async_update_data()) == {"online": True}
    assert attempts == 2
