"""Unit tests for pending-write verification in the Ariston coordinator."""

import asyncio
from pathlib import Path
import sys

import pytest

CLONE_ROOT = Path(__file__).resolve().parent.parent
if str(CLONE_ROOT) not in sys.path:
    sys.path.insert(0, str(CLONE_ROOT))

from custom_components.ariston.coordinator import (  # noqa: E402
    DeviceDataUpdateCoordinator,
    PendingWrite,
)


class _FakeDevice:
    """Minimal stand-in exposing the water-heater read/write surface."""

    water_heater_target_temperature = 40.0
    water_heater_current_mode_text = "Auto"

    def __init__(self) -> None:
        self.temperature_writes: list[float] = []
        self.mode_writes: list[str] = []

    async def async_set_water_heater_temperature(self, value) -> None:
        self.temperature_writes.append(value)

    async def async_set_water_heater_operation_mode(self, value) -> None:
        self.mode_writes.append(value)


def _coordinator_with(device: _FakeDevice) -> DeviceDataUpdateCoordinator:
    """Build a coordinator without hass: only the fields under test."""
    coordinator = DeviceDataUpdateCoordinator.__new__(DeviceDataUpdateCoordinator)
    coordinator.device = device
    coordinator.pending_writes = {}
    return coordinator


def _check(coordinator: DeviceDataUpdateCoordinator) -> None:
    asyncio.run(coordinator._async_check_pending_writes())


def test_pending_write_cleared_on_match():
    device = _FakeDevice()
    device.water_heater_target_temperature = 55.0
    coordinator = _coordinator_with(device)
    coordinator.pending_writes["temperature"] = PendingWrite(
        prop="temperature", expected=55
    )

    _check(coordinator)

    assert coordinator.pending_writes == {}  # verified, cleared
    assert device.temperature_writes == []  # no extra write issued


def test_pending_write_retries_on_mismatch():
    device = _FakeDevice()
    device.water_heater_target_temperature = 40.0  # device ignored the write
    coordinator = _coordinator_with(device)
    coordinator.pending_writes["temperature"] = PendingWrite(
        prop="temperature", expected=55
    )

    _check(coordinator)

    assert device.temperature_writes == [55]  # written again exactly once
    assert coordinator.pending_writes["temperature"].tries == 1
    assert coordinator.pending_writes["temperature"].expected == 55


def test_pending_write_gives_up_after_max_tries(caplog):
    device = _FakeDevice()
    device.water_heater_target_temperature = 40.0
    coordinator = _coordinator_with(device)
    coordinator.pending_writes["temperature"] = PendingWrite(
        prop="temperature", expected=55, tries=3, max_tries=3
    )

    with caplog.at_level("WARNING"):
        _check(coordinator)

    assert coordinator.pending_writes == {}  # cleared, never a write loop
    assert device.temperature_writes == []  # no further writes
    assert any("gave up" in record.getMessage() for record in caplog.records)


def test_retry_write_failure_does_not_raise():
    device = _FakeDevice()
    device.water_heater_target_temperature = 40.0

    async def broken_write(value):
        raise ConnectionError("429 blocked")

    device.async_set_water_heater_temperature = broken_write
    coordinator = _coordinator_with(device)
    coordinator.pending_writes["temperature"] = PendingWrite(
        prop="temperature", expected=55
    )

    _check(coordinator)  # must not raise

    assert coordinator.pending_writes["temperature"].tries == 1  # retry next poll


def test_update_and_verify_wraps_poll_and_runs_hook_after():
    """The wiring itself: poll result is returned, verify hook runs after it."""
    coordinator = DeviceDataUpdateCoordinator.__new__(DeviceDataUpdateCoordinator)
    calls: list[str] = []

    async def fake_poll():
        calls.append("poll")
        return {"state": "fresh"}

    async def fake_check():
        calls.append("verify")

    coordinator._async_device_update_state = fake_poll
    coordinator._async_check_pending_writes = fake_check

    result = asyncio.run(coordinator._async_update_and_verify())

    assert result == {"state": "fresh"}  # coordinator.data contract preserved
    assert calls == ["poll", "verify"]  # hook only after a successful poll
