"""Regression tests for Ariston integration behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import homeassistant  # noqa: F401  # Install Home Assistant's schema compatibility
import pytest
from ariston import ConnectionException, DeviceAttribute
from homeassistant.helpers.update_coordinator import UpdateFailed

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
