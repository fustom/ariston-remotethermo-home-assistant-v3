"""Tests for poll-based write confirmation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import homeassistant  # noqa: F401  # Install Home Assistant's schema compatibility
import pytest
from ariston import ConnectionException
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ariston.const import ARISTON_WATER_HEATER_TYPES
from custom_components.ariston.coordinator import (
    DeviceDataUpdateCoordinator,
    PendingWrite,
)
from custom_components.ariston.water_heater import AristonWaterHeater


class WriteRecorder:
    """Record real retry behavior without an external device call."""

    def __init__(self, *, fail: bool = False) -> None:
        self.attempts = 0
        self.fail = fail

    async def retry(self) -> None:
        self.attempts += 1
        if self.fail:
            raise ConnectionException("offline")


def _coordinator(update=None) -> DeviceDataUpdateCoordinator:
    if update is None:

        async def update():
            return None

    return DeviceDataUpdateCoordinator(
        object(),
        None,
        SimpleNamespace(name="Boiler"),
        180,
        "state",
        update,
    )


def test_pending_write_defaults_to_three_reissues() -> None:
    """Keep command retries finite and independent from polling retries."""
    pending = PendingWrite(1, lambda: 0, WriteRecorder().retry)

    assert pending.max_retries == 3
    assert pending.retries == 0


def test_matching_pending_write_is_removed_without_reissue() -> None:
    """Confirm a write from refreshed state without another command."""
    coordinator = _coordinator()
    writes = WriteRecorder()
    coordinator.track_pending_write(
        "temperature", 55.0, lambda: 55.0, writes.retry, tolerance=0.1
    )

    asyncio.run(coordinator._async_check_pending_writes())

    assert coordinator.pending_writes == {}
    assert writes.attempts == 0


def test_temperature_tolerance_accepts_rounding() -> None:
    """Accept harmless cloud serialization differences."""
    coordinator = _coordinator()
    writes = WriteRecorder()
    coordinator.track_pending_write(
        "temperature", 48.9, lambda: 48.89, writes.retry, tolerance=0.05
    )

    asyncio.run(coordinator._async_check_pending_writes())

    assert coordinator.pending_writes == {}


def test_new_command_replaces_older_pending_command() -> None:
    """Never replay an obsolete target after a newer command."""
    coordinator = _coordinator()
    writes = WriteRecorder()
    coordinator.track_pending_write("temperature", 50.0, lambda: 40.0, writes.retry)
    coordinator.track_pending_write("temperature", 60.0, lambda: 40.0, writes.retry)

    assert coordinator.pending_writes["temperature"].expected == 60.0


def test_mismatch_reissues_once_and_keeps_pending_write() -> None:
    """Use the next normal poll to trigger one command reissue."""
    coordinator = _coordinator()
    writes = WriteRecorder()
    coordinator.track_pending_write("mode", "eco", lambda: "manual", writes.retry)

    asyncio.run(coordinator._async_check_pending_writes())

    assert writes.attempts == 1
    assert coordinator.pending_writes["mode"].retries == 1


def test_failed_reissue_counts_toward_limit() -> None:
    """Prevent connection failures from creating endless command retries."""
    coordinator = _coordinator()
    writes = WriteRecorder(fail=True)
    coordinator.track_pending_write("mode", "eco", lambda: "manual", writes.retry)

    asyncio.run(coordinator._async_check_pending_writes())

    assert writes.attempts == 1
    assert coordinator.pending_writes["mode"].retries == 1


def test_three_reissues_remove_unconfirmed_write() -> None:
    """Stop replaying a command after three post-write attempts."""
    coordinator = _coordinator()
    writes = WriteRecorder()
    coordinator.track_pending_write("mode", "eco", lambda: "manual", writes.retry)

    for _ in range(3):
        asyncio.run(coordinator._async_check_pending_writes())

    assert writes.attempts == 3
    assert coordinator.pending_writes == {}


def test_inflight_retry_cannot_remove_replacement() -> None:
    """Keep a newer command registered when an older retry finishes."""
    coordinator = _coordinator()

    async def replace_command() -> None:
        coordinator.track_pending_write(
            "temperature", 60.0, lambda: 40.0, WriteRecorder().retry
        )

    coordinator.track_pending_write(
        "temperature", 50.0, lambda: 40.0, replace_command
    )
    coordinator.pending_writes["temperature"].max_retries = 1

    asyncio.run(coordinator._async_check_pending_writes())

    assert coordinator.pending_writes["temperature"].expected == 60.0


def test_snapshot_does_not_reissue_a_later_replaced_command() -> None:
    """Skip an obsolete snapshot entry replaced while an earlier retry awaited."""
    coordinator = _coordinator()
    obsolete_mode = WriteRecorder()
    replacement_mode = WriteRecorder()

    async def replace_mode() -> None:
        coordinator.track_pending_write(
            "mode", "eco", lambda: "manual", replacement_mode.retry
        )

    coordinator.track_pending_write(
        "temperature", 50.0, lambda: 40.0, replace_mode
    )
    coordinator.track_pending_write(
        "mode", "boost", lambda: "manual", obsolete_mode.retry
    )

    asyncio.run(coordinator._async_check_pending_writes())

    assert obsolete_mode.attempts == 0
    assert coordinator.pending_writes["mode"].expected == "eco"


def test_operation_mode_uses_exact_equality() -> None:
    """Confirm nonnumeric values with exact equality."""
    coordinator = _coordinator()
    writes = WriteRecorder()
    coordinator.track_pending_write("mode", "eco", lambda: "eco", writes.retry)

    asyncio.run(coordinator._async_check_pending_writes())

    assert coordinator.pending_writes == {}
    assert writes.attempts == 0


def test_successful_normal_poll_checks_pending_writes_without_extra_read() -> None:
    """Verify only after the existing scheduled device update."""
    update_attempts = 0
    actual = 40.0

    async def update():
        nonlocal actual, update_attempts
        update_attempts += 1
        actual = 55.0
        return {"online": True}

    coordinator = _coordinator(update)
    writes = WriteRecorder()
    coordinator.track_pending_write(
        "temperature", 55.0, lambda: actual, writes.retry, tolerance=0.05
    )

    result = asyncio.run(coordinator._async_update_data())

    assert result == {"online": True}
    assert update_attempts == 1
    assert coordinator.pending_writes == {}
    assert writes.attempts == 0


def test_failed_normal_poll_does_not_reissue_pending_write() -> None:
    """Wait for valid refreshed state before judging a command."""

    async def update():
        raise ConnectionException("offline")

    coordinator = _coordinator(update)
    writes = WriteRecorder()
    coordinator.track_pending_write("mode", "eco", lambda: "manual", writes.retry)

    with pytest.raises(UpdateFailed):
        asyncio.run(coordinator._async_update_data())

    assert writes.attempts == 0
    assert coordinator.pending_writes["mode"].retries == 0


def _water_heater():
    temperature_writes = []
    mode_writes = []

    async def set_temperature(value):
        temperature_writes.append(value)

    async def set_mode(value):
        mode_writes.append(value)

    device = SimpleNamespace(
        name="Boiler",
        gateway="gw",
        water_heater_temperature_step=1.0,
        water_heater_target_temperature=40.0,
        water_heater_current_mode_text="manual",
        async_set_water_heater_temperature=set_temperature,
        async_set_water_heater_operation_mode=set_mode,
    )
    coordinator = DeviceDataUpdateCoordinator(
        object(), None, device, 180, "state", WriteRecorder().retry
    )
    entity = AristonWaterHeater(coordinator, ARISTON_WATER_HEATER_TYPES[0])
    entity.async_write_ha_state = lambda: None
    return entity, temperature_writes, mode_writes


def test_successful_water_heater_writes_are_registered_for_confirmation() -> None:
    """Track target and mode only after their original commands succeed."""
    entity, temperature_writes, mode_writes = _water_heater()

    asyncio.run(entity.async_set_temperature(**{ATTR_TEMPERATURE: 55.0}))
    asyncio.run(entity.async_set_operation_mode("eco"))

    assert temperature_writes == [55.0]
    assert mode_writes == ["eco"]
    assert entity.coordinator.pending_writes["water_heater_temperature"].expected == 55.0
    assert entity.coordinator.pending_writes["water_heater_operation_mode"].expected == "eco"


def test_late_older_temperature_completion_cannot_replace_newer_target() -> None:
    """Keep request ordering when two original setters finish out of order."""
    entity, _, _ = _water_heater()

    async def exercise_race() -> None:
        older_started = asyncio.Event()
        release_older = asyncio.Event()

        async def set_temperature(value) -> None:
            if value == 50.0:
                older_started.set()
                await release_older.wait()

        entity.device.async_set_water_heater_temperature = set_temperature
        older = asyncio.create_task(
            entity.async_set_temperature(**{ATTR_TEMPERATURE: 50.0})
        )
        await older_started.wait()
        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 60.0})
        release_older.set()
        await older

    asyncio.run(exercise_race())

    assert (
        entity.coordinator.pending_writes["water_heater_temperature"].expected
        == 60.0
    )
