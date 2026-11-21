"""Recorder edge cases of the daily consumption sensors (PR #532 review).

- Midnight: a revision of yesterday's last bucket that arrives with the
  first fetch of the new day must be booked under yesterday's last_reset.
- Upgrade: the first values after the upgrade must not be compared with
  what the same entity reported before, so a baseline cycle is started.
  A new sensor has no statistics to keep and reports today's total.
- Failed fetch: an unavailable update must not close yesterday's cycle.

Runs in Europe/Rome; the cloud's v[] has 24 hourly buckets, v[23] = now.
"""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import zoneinfo

import pytest
from ariston.const import ConsumptionTimeInterval, ConsumptionType
from homeassistant.helpers.restore_state import RestoredExtraData
from homeassistant.util import dt as dt_util

from custom_components.ariston.const import ARISTON_SENSOR_TYPES
from custom_components.ariston.energy import previous_day_total
from custom_components.ariston.sensor import (
    DAILY_CONSUMPTION_SCHEME,
    AristonDailyConsumptionSensor,
    AristonSensor,
    async_setup_entry,
)

ROME = zoneinfo.ZoneInfo("Europe/Rome")
DHW = ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY
DAY = ConsumptionTimeInterval.LAST_DAY


@pytest.fixture(autouse=True)
async def rome_time_zone(hass):
    """Run in Europe/Rome; the hass fixture sets its own zone first."""
    await hass.config.async_set_time_zone("Europe/Rome")


def _midnight(day: int) -> dt.datetime:
    return dt.datetime(2026, 5, day, tzinfo=ROME)


def _set_buckets(device, values):
    device.consumptions_sequences = [{"k": DHW.value, "p": DAY.value, "v": values}]


def _description():
    return next(d for d in ARISTON_SENSOR_TYPES if d.daily_consumption_type == DHW)


def _new_entity(hass, coordinator):
    entity = AristonDailyConsumptionSensor(coordinator, _description())
    entity.hass = hass
    entity.entity_id = "sensor.dhw_total"
    return entity


async def _sensor(hass, coordinator, restored=None, *, legacy=True):
    """Return an added sensor whose state writes are collected in `writes`.

    `legacy`: Recorder holds statistics from before the upgrade.
    """
    entity = _new_entity(hass, coordinator)
    entity.async_get_last_extra_data = AsyncMock(
        return_value=None if restored is None else RestoredExtraData(restored)
    )
    entity._has_statistics = AsyncMock(return_value=legacy)
    entity.writes = []
    entity.async_write_ha_state = lambda: entity.writes.append(
        (entity.native_value, entity.last_reset)
    )
    await entity.async_added_to_hass()
    return entity


def _current_scheme():
    return {"scheme": DAILY_CONSUMPTION_SCHEME}


async def test_revised_last_bucket_is_booked_under_yesterday(
    hass, coordinator, ariston_device, freezer
):
    """The reviewer's example: 23:00 bucket goes 0.2 -> 0.8 after midnight."""
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.2])
    entity = await _sensor(hass, coordinator, _current_scheme())
    assert entity.native_value == pytest.approx(2.5)
    assert entity.last_reset == _midnight(6)

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.0])
    entity._handle_coordinator_update()

    assert entity.writes == [
        (pytest.approx(3.1), _midnight(6)),  # closing under yesterday's reset
        (pytest.approx(0.0), _midnight(7)),
    ]


async def test_no_closing_write_when_yesterday_did_not_change(
    hass, coordinator, ariston_device, freezer
):
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity = await _sensor(hass, coordinator, _current_scheme())

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.0])
    entity._handle_coordinator_update()

    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]


async def test_no_closing_write_without_full_history(
    hass, coordinator, ariston_device, freezer
):
    """After a restart yesterday's first hour is unknown: do not guess."""
    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.0])
    entity = await _sensor(hass, coordinator, _current_scheme())
    entity._published = (2.5, _midnight(6), 0.0)

    entity._handle_coordinator_update()

    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]


async def test_no_closing_write_for_an_older_cycle(
    hass, coordinator, ariston_device, freezer
):
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity = await _sensor(hass, coordinator, _current_scheme())
    entity._published = (0.5, _midnight(4), 0.0)

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.0])
    entity._handle_coordinator_update()

    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]


async def test_upgrade_starts_a_baseline_cycle(
    hass, coordinator, ariston_device, freezer
):
    """Usage before the upgrade was already recorded: start from zero."""
    upgrade = dt.datetime(2026, 5, 6, 14, 20, tzinfo=ROME)
    freezer.move_to(upgrade)
    _set_buckets(ariston_device, [0.1] * 24)  # 15 buckets today -> 1.5
    entity = await _sensor(hass, coordinator, restored=None)

    assert entity.native_value == pytest.approx(0.0)
    assert entity.last_reset == upgrade
    assert entity.extra_restore_state_data.as_dict() == {
        "scheme": DAILY_CONSUMPTION_SCHEME,
        "baseline": pytest.approx(1.5),
        "baseline_reset": dt_util.as_utc(upgrade).isoformat(),
    }

    freezer.move_to(dt.datetime(2026, 5, 6, 15, 20, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.3])
    entity._handle_coordinator_update()
    assert entity.writes[-1] == (pytest.approx(0.3), upgrade)

    # Midnight: close the baseline cycle, then return to local midnight.
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity._handle_coordinator_update()
    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.4, 0.0])
    entity.writes.clear()
    entity._handle_coordinator_update()

    assert entity.writes == [
        (pytest.approx(2.7 - 1.5), upgrade),
        (pytest.approx(0.0), _midnight(7)),
    ]
    assert entity.extra_restore_state_data.as_dict() == {
        "scheme": DAILY_CONSUMPTION_SCHEME
    }


async def test_baseline_survives_a_restart(hass, coordinator, ariston_device, freezer):
    upgrade = dt.datetime(2026, 5, 6, 14, 20, tzinfo=ROME)
    freezer.move_to(dt.datetime(2026, 5, 6, 18, 0, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)  # 19 buckets today -> 1.9
    entity = await _sensor(
        hass,
        coordinator,
        {
            "scheme": DAILY_CONSUMPTION_SCHEME,
            "baseline": 1.5,
            "baseline_reset": dt_util.as_utc(upgrade).isoformat(),
        },
    )

    assert entity.native_value == pytest.approx(0.4)
    assert entity.last_reset == upgrade


async def test_expired_baseline_is_dropped_on_restart(
    hass, coordinator, ariston_device, freezer
):
    freezer.move_to(dt.datetime(2026, 5, 7, 9, 0, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity = await _sensor(
        hass,
        coordinator,
        {
            "scheme": DAILY_CONSUMPTION_SCHEME,
            "baseline": 1.5,
            "baseline_reset": "2026-05-06T12:20:00+00:00",
        },
    )

    assert entity.native_value == pytest.approx(1.0)
    assert entity.last_reset == _midnight(7)


async def test_upgrade_waits_for_data(hass, coordinator, ariston_device, freezer):
    freezer.move_to(dt.datetime(2026, 5, 6, 14, 20, tzinfo=ROME))
    ariston_device.consumptions_sequences = []
    entity = await _sensor(hass, coordinator, restored=None)

    assert entity.native_value is None
    assert entity.extra_restore_state_data is None

    later = dt.datetime(2026, 5, 6, 14, 40, tzinfo=ROME)
    freezer.move_to(later)
    _set_buckets(ariston_device, [0.1] * 24)
    entity._handle_coordinator_update()

    assert entity.writes == [(pytest.approx(0.0), later)]


def test_previous_day_total_needs_24_buckets(ariston_device):
    _set_buckets(ariston_device, [0.1] * 5)
    assert previous_day_total(ariston_device, DHW) is None


async def test_setup_uses_daily_class_only_for_daily_sensors(hass, coordinator):
    from custom_components.ariston.const import DOMAIN, ENERGY_COORDINATOR

    coordinator.device.are_device_features_available = lambda *args: True
    entry = type(
        "Entry", (), {"unique_id": "uid", "async_on_unload": lambda self, f: None}
    )()
    hass.data[DOMAIN] = {"uid": {"coordinator": coordinator, ENERGY_COORDINATOR: coordinator}}
    added = []
    await async_setup_entry(hass, entry, added.extend)

    daily = [e for e in added if isinstance(e, AristonDailyConsumptionSensor)]
    assert len(daily) == 8
    assert all(e.entity_description.daily_consumption_type for e in daily)
    assert any(type(e) is AristonSensor for e in added)


async def test_new_sensor_reports_todays_total(
    hass, coordinator, ariston_device, freezer
):
    """No restore data and no statistics: a new sensor, not an upgrade."""
    freezer.move_to(dt.datetime(2026, 5, 6, 14, 20, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity = await _sensor(hass, coordinator, restored=None, legacy=False)

    assert entity.native_value == pytest.approx(1.5)
    assert entity.last_reset == _midnight(6)
    assert entity.extra_restore_state_data.as_dict() == _current_scheme()


async def test_failed_midnight_poll_keeps_yesterday_open(
    hass, coordinator, ariston_device, freezer
):
    """The next successful fetch still books yesterday's revised bucket."""
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.2])
    entity = await _sensor(hass, coordinator, _current_scheme())

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    coordinator.last_update_success = False
    entity._handle_coordinator_update()
    assert entity._published == (pytest.approx(2.5), _midnight(6), 0.0)

    freezer.move_to(dt.datetime(2026, 5, 7, 1, 5, tzinfo=ROME))
    coordinator.last_update_success = True
    _set_buckets(ariston_device, [0.1] * 21 + [0.8, 0.0, 0.1])
    entity.writes.clear()
    entity._handle_coordinator_update()

    assert entity.writes == [
        (pytest.approx(3.1), _midnight(6)),
        (pytest.approx(0.1), _midnight(7)),
    ]


async def test_missing_value_does_not_replace_the_published_cycle(
    hass, coordinator, ariston_device, freezer
):
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity = await _sensor(hass, coordinator, _current_scheme())

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    ariston_device.consumptions_sequences = []
    entity._handle_coordinator_update()

    assert entity._published == (pytest.approx(2.4), _midnight(6), 0.0)


async def test_revised_last_bucket_with_fractional_offset(
    hass, coordinator, ariston_device, freezer
):
    """Asia/Kolkata (UTC+5:30): local midnight is not on a whole UTC hour."""
    await hass.config.async_set_time_zone("Asia/Kolkata")
    kolkata = zoneinfo.ZoneInfo("Asia/Kolkata")
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 10, tzinfo=kolkata))
    _set_buckets(ariston_device, [0.1] * 23 + [0.2])
    entity = await _sensor(hass, coordinator, _current_scheme())
    assert entity.native_value == pytest.approx(2.5)

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 10, tzinfo=kolkata))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.05])
    entity._handle_coordinator_update()

    assert entity.writes == [
        (pytest.approx(3.1), dt.datetime(2026, 5, 6, tzinfo=kolkata)),
        (pytest.approx(0.05), dt.datetime(2026, 5, 7, tzinfo=kolkata)),
    ]


async def test_has_statistics_without_recorder(hass, coordinator):
    entity = _new_entity(hass, coordinator)
    assert "recorder" not in hass.config.components
    assert await entity._has_statistics() is False


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [({"sensor.dhw_total": (1, {})}, True), ({}, False)],
)
async def test_has_statistics_reads_recorder_metadata(
    hass, coordinator, metadata, expected
):
    entity = _new_entity(hass, coordinator)
    hass.config.components.add("recorder")
    calls = []

    def get_metadata(hass_arg, *, statistic_ids):
        calls.append(statistic_ids)
        return metadata

    async def run(job):
        return job()

    recorder = SimpleNamespace(async_add_executor_job=run)
    with (
        patch("custom_components.ariston.sensor.get_instance", return_value=recorder),
        patch("custom_components.ariston.sensor.get_metadata", get_metadata),
    ):
        assert await entity._has_statistics() is expected
    assert calls == [{"sensor.dhw_total"}]


async def test_has_statistics_assumes_upgrade_on_recorder_error(hass, coordinator):
    entity = _new_entity(hass, coordinator)
    hass.config.components.add("recorder")
    with patch(
        "custom_components.ariston.sensor.get_instance", side_effect=KeyError("db")
    ):
        assert await entity._has_statistics() is True



async def test_baseline_cycle_closes_after_an_empty_midnight_fetch(
    hass, coordinator, ariston_device, freezer
):
    """The baseline ends at midnight even when the first fetch has no data.

    The closing must still exclude it, or the usage from before the upgrade
    is counted again.
    """
    upgrade = dt.datetime(2026, 5, 6, 14, 20, tzinfo=ROME)
    freezer.move_to(upgrade)
    _set_buckets(ariston_device, [0.1] * 24)  # baseline 1.5
    entity = await _sensor(hass, coordinator, restored=None)
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity._handle_coordinator_update()  # 2.4 - 1.5

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    ariston_device.consumptions_sequences = []
    entity._handle_coordinator_update()
    assert entity._baseline_reset is None

    freezer.move_to(dt.datetime(2026, 5, 7, 1, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 21 + [0.4, 0.0, 0.1])
    entity.writes.clear()
    entity._handle_coordinator_update()

    assert entity.writes == [
        (pytest.approx(2.7 - 1.5), upgrade),
        (pytest.approx(0.1), _midnight(7)),
    ]
