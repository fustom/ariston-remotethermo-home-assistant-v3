"""Recorder edge cases of the daily consumption sensors (PR #532 review).

- Midnight: a revision of yesterday's last bucket that arrives with the
  first fetch of the new day must be booked in yesterday's statistics,
  not under a state written after midnight (that would count as today).
- Upgrade: the first values after the upgrade must not be compared with
  what the same entity reported before, so a baseline cycle is started.
  A new sensor has no statistics to keep and reports today's total.
- Failed fetch: an unavailable update must not close yesterday's cycle.

Runs in Europe/Rome; the cloud's v[] has 24 hourly buckets, v[23] = now.
"""

import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import zoneinfo

import pytest
from ariston.const import ConsumptionTimeInterval, ConsumptionType
from homeassistant.helpers.restore_state import RestoredExtraData
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.ariston.const import ARISTON_SENSOR_TYPES
from custom_components.ariston.energy import previous_day_total
from custom_components.ariston.revision import RevisionResult
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
    entity.booked = []

    def book():
        # Recorder confirms every queued revision.
        for reset, total in entity._revisions.items():
            entity.booked.append((reset, pytest.approx(total)))
        entity._revisions.clear()

    entity._book_revisions = book
    # Updates are driven by the tests, not by scheduled refreshes.
    with patch.object(coordinator, "async_add_listener", return_value=lambda: None):
        await entity.async_added_to_hass()
    return entity


async def _drain():
    """Run the booking tasks without firing scheduled coordinator refreshes."""
    for _ in range(3):
        await asyncio.sleep(0)


def _closed(reset: dt.datetime, total: float):
    """A booked revision: yesterday's cycle and its final total."""
    return (dt_util.as_utc(reset), pytest.approx(total))


def _current_scheme():
    return {"scheme": DAILY_CONSUMPTION_SCHEME}


def _saved(entity):
    """The restore data without the history and the last published value."""
    data = dict(entity.extra_restore_state_data.as_dict())
    data.pop("history", None)
    data.pop("published", None)
    return data


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
    await _drain()

    # No state under yesterday's reset: the 0.6 goes into yesterday's 23:00.
    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]
    assert entity.booked == [_closed(_midnight(6), 3.1)]


async def test_no_closing_write_when_yesterday_did_not_change(
    hass, coordinator, ariston_device, freezer
):
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity = await _sensor(hass, coordinator, _current_scheme())

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.0])
    entity._handle_coordinator_update()
    await _drain()

    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]
    assert entity.booked == []


async def test_no_closing_write_without_full_history(
    hass, coordinator, ariston_device, freezer
):
    """After a restart yesterday's first hour is unknown: do not guess."""
    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.0])
    entity = await _sensor(hass, coordinator, _current_scheme())
    entity._published = (2.5, _midnight(6), 0.0)

    entity._handle_coordinator_update()
    await _drain()

    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]
    assert entity.booked == []


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
    await _drain()

    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]
    assert entity.booked == []


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
    assert _saved(entity) == {
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
    await _drain()

    # Published 2.4 - 1.5 at 23:05; yesterday ends at 2.7 - 1.5.
    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]
    assert entity.booked == [_closed(upgrade, 1.2)]
    assert _saved(entity) == {
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
    assert _saved(entity) == _current_scheme()


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
    await _drain()

    assert entity.writes == [(pytest.approx(0.1), _midnight(7))]
    assert entity.booked == [_closed(_midnight(6), 3.1)]


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
    await _drain()

    assert entity.writes == [
        (pytest.approx(0.05), dt.datetime(2026, 5, 7, tzinfo=kolkata)),
    ]
    # Yesterday's last bucket is 17:00-18:00 UTC (22:30-23:30 local).
    assert entity.booked == [_closed(dt.datetime(2026, 5, 6, tzinfo=kolkata), 3.1)]


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
    await _drain()

    assert entity.writes == [(pytest.approx(0.1), _midnight(7))]
    assert entity.booked == [_closed(upgrade, 1.2)]


async def _restart(hass, coordinator, ariston_device, entity):
    """Restart: drop the in-memory history, restore a new entity, add it."""
    saved = dict(entity.extra_restore_state_data.as_dict())
    del ariston_device._ha_hourly_history
    restarted = await _sensor(hass, coordinator, saved)
    restarted.async_write_ha_state()  # the state HA writes after adding
    await _drain()
    return restarted


async def test_restart_across_midnight_still_closes_yesterday(
    hass, coordinator, ariston_device, freezer
):
    """History and last value come from the restore data.

    The fetch at 00:05 no longer holds yesterday's 00:00 bucket, so the
    closing needs the saved history.
    """
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.2])
    entity = await _sensor(hass, coordinator, _current_scheme())

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.0])
    restarted = await _restart(hass, coordinator, ariston_device, entity)

    assert restarted.writes == [(pytest.approx(0.0), _midnight(7))]
    assert restarted.booked == [_closed(_midnight(6), 3.1)]
    assert restarted._published == (pytest.approx(0.0), _midnight(7), 0.0)


async def test_restart_during_the_day_writes_one_state(
    hass, coordinator, ariston_device, freezer
):
    freezer.move_to(dt.datetime(2026, 5, 6, 14, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity = await _sensor(hass, coordinator, _current_scheme())

    freezer.move_to(dt.datetime(2026, 5, 6, 15, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    restarted = await _restart(hass, coordinator, ariston_device, entity)

    assert restarted.writes == [(pytest.approx(1.6), _midnight(6))]


async def test_restart_across_midnight_closes_the_baseline_cycle(
    hass, coordinator, ariston_device, freezer
):
    upgrade = dt.datetime(2026, 5, 6, 14, 20, tzinfo=ROME)
    freezer.move_to(upgrade)
    _set_buckets(ariston_device, [0.1] * 24)  # baseline 1.5
    entity = await _sensor(hass, coordinator, restored=None)
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 24)
    entity._handle_coordinator_update()

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.4, 0.0])
    restarted = await _restart(hass, coordinator, ariston_device, entity)

    assert restarted.writes == [(pytest.approx(0.0), _midnight(7))]
    assert restarted.booked == [_closed(upgrade, 1.2)]
    assert _saved(restarted) == _current_scheme()


@pytest.mark.parametrize(
    "published",
    [None, "x", [1.0, "2026-05-06T00:00:00"], [1.0, "2026-05-06T00:00:00", 0.0],
     ["a", "2026-05-06T00:00:00+02:00", 0.0], [1.0, 5, 0.0]],
)
async def test_invalid_saved_value_is_ignored(
    hass, coordinator, ariston_device, freezer, published
):
    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.0])
    entity = await _sensor(
        hass, coordinator, {**_current_scheme(), "published": published}
    )
    entity.async_write_ha_state()
    await hass.async_block_till_done()

    assert entity.writes == [(pytest.approx(0.0), _midnight(7))]


async def test_update_right_after_a_startup_closing_does_not_close_twice(
    hass, coordinator, ariston_device, freezer
):
    """A coordinator update can run before the startup booking task."""
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.2])
    entity = await _sensor(hass, coordinator, _current_scheme())
    saved = dict(entity.extra_restore_state_data.as_dict())
    del ariston_device._ha_hourly_history

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.0])
    restarted = await _sensor(hass, coordinator, saved)
    restarted.async_write_ha_state()  # the state HA writes after adding
    restarted._handle_coordinator_update()  # before the booking task runs
    await hass.async_block_till_done()

    freezer.move_to(dt.datetime(2026, 5, 7, 1, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.0, 0.1])
    restarted._handle_coordinator_update()
    await _drain()

    assert restarted.writes == [
        (pytest.approx(0.0), _midnight(7)),
        (pytest.approx(0.0), _midnight(7)),
        (pytest.approx(0.1), _midnight(7)),
    ]
    assert restarted.booked == [_closed(_midnight(6), 3.1)]  # once


async def test_unconfirmed_revision_survives_a_restart(
    hass, coordinator, ariston_device, freezer
):
    """Reviewer's crash case: the restore data can be saved or stale.

    A revision Recorder has not confirmed is kept in the restore data and
    queued again after the restart; yesterday's final total is published,
    so no second closing is computed on top of it.
    """
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.2])
    entity = await _sensor(hass, coordinator, _current_scheme())
    entity._book_revisions = lambda: None  # Recorder never confirms.

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.0])
    entity._handle_coordinator_update()
    saved = dict(entity.extra_restore_state_data.as_dict())
    assert saved["revisions"] == {
        dt_util.as_utc(_midnight(6)).isoformat(): pytest.approx(3.1)
    }

    restarted = await _restart(hass, coordinator, ariston_device, entity)
    assert restarted.booked == [_closed(_midnight(6), 3.1)]
    assert restarted.writes == [(pytest.approx(0.0), _midnight(7))]


async def test_stale_restore_data_queues_the_same_revision_again(
    hass, coordinator, ariston_device, freezer
):
    """Restore data saved before the closing: the closing runs again.

    Recorder's rows already hold yesterday's final total, so booking the
    same revision a second time changes nothing (see test_revision.py).
    """
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.2])
    entity = await _sensor(hass, coordinator, _current_scheme())
    stale = dict(entity.extra_restore_state_data.as_dict())

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 22 + [0.8, 0.0])
    entity._handle_coordinator_update()
    assert entity.booked == [_closed(_midnight(6), 3.1)]

    del ariston_device._ha_hourly_history
    restarted = await _sensor(hass, coordinator, stale)
    assert restarted.booked == [_closed(_midnight(6), 3.1)]  # same total



async def test_all_null_reply_does_not_skip_the_closing(
    hass, coordinator, ariston_device, freezer
):
    """Reviewer's case: a 24-slot reply of nulls right after midnight."""
    freezer.move_to(dt.datetime(2026, 5, 6, 23, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 23 + [0.2])
    entity = await _sensor(hass, coordinator, _current_scheme())

    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [None] * 24)
    entity._handle_coordinator_update()
    assert entity.writes[-1] == (None, _midnight(7))  # unknown, not 0
    assert entity._published == (pytest.approx(2.5), _midnight(6), 0.0)

    freezer.move_to(dt.datetime(2026, 5, 7, 1, 5, tzinfo=ROME))
    _set_buckets(ariston_device, [0.1] * 21 + [0.8, 0.0, 0.1])
    entity.writes.clear()
    entity._handle_coordinator_update()
    await _drain()

    assert entity.writes == [(pytest.approx(0.1), _midnight(7))]
    assert entity.booked == [_closed(_midnight(6), 3.1)]


class _FakeRecorder:
    def __init__(self):
        self.tasks = []

    def queue_task(self, task):
        self.tasks.append(task)


async def _booking_entity(hass, coordinator, revisions):
    entity = _new_entity(hass, coordinator)
    entity.async_get_last_extra_data = AsyncMock(
        return_value=RestoredExtraData(
            {
                **_current_scheme(),
                "revisions": {
                    dt_util.as_utc(reset).isoformat(): total
                    for reset, total in revisions.items()
                },
            }
        )
    )
    hass.config.components.add("recorder")
    recorder = _FakeRecorder()
    with (
        patch("custom_components.ariston.sensor.get_instance", return_value=recorder),
        patch.object(coordinator, "async_add_listener", return_value=lambda: None),
    ):
        await entity.async_added_to_hass()
    return entity, recorder


async def test_revisions_are_sent_to_recorder(hass, coordinator, freezer):
    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    entity, recorder = await _booking_entity(
        hass, coordinator, {_midnight(6): 3.1, _midnight(5): 2.0}
    )

    (task,) = recorder.tasks
    assert {(r.last_reset, r.total, r.unit) for r in task.revisions} == {
        (dt_util.as_utc(_midnight(6)), 3.1, entity.native_unit_of_measurement),
        (dt_util.as_utc(_midnight(5)), 2.0, entity.native_unit_of_measurement),
    }
    revision = next(r for r in task.revisions if r.total == 3.1)
    assert revision.statistic_id == "sensor.dhw_total"
    assert revision.cycle_end == dt_util.as_utc(_midnight(7))

    # One batch at a time.
    with patch("custom_components.ariston.sensor.get_instance", return_value=recorder):
        entity._book_revisions()
    assert len(recorder.tasks) == 1

    task.on_done({r: RevisionResult.BOOKED for r in task.revisions})
    assert entity._revisions == {}
    assert entity._retry_unsub is None


async def test_unbooked_revision_is_retried(hass, coordinator, freezer):
    freezer.move_to(dt.datetime(2026, 5, 7, 0, 1, tzinfo=ROME))
    entity, recorder = await _booking_entity(
        hass, coordinator, {_midnight(6): 3.1, _midnight(5): 2.0}
    )
    (task,) = recorder.tasks
    results = {
        r: RevisionResult.NOT_READY if r.total == 3.1 else RevisionResult.UNCHANGED
        for r in task.revisions
    }
    task.on_done(results)
    assert entity._revisions == {dt_util.as_utc(_midnight(6)): 3.1}
    assert entity._retry_unsub is not None

    freezer.tick(dt.timedelta(minutes=5))
    with patch("custom_components.ariston.sensor.get_instance", return_value=recorder):
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert len(recorder.tasks) == 2
    assert entity._retry_unsub is None

    recorder.tasks[1].on_done(
        dict.fromkeys(recorder.tasks[1].revisions, RevisionResult.FAILED)
    )
    assert entity._retry_unsub is not None
    await entity.async_will_remove_from_hass()
    assert entity._retry_unsub is None


async def test_revision_changed_while_booking_is_kept(hass, coordinator, freezer):
    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    entity, recorder = await _booking_entity(hass, coordinator, {_midnight(6): 3.1})
    (task,) = recorder.tasks
    entity._revisions[dt_util.as_utc(_midnight(6))] = 3.3  # a later revision
    with patch("custom_components.ariston.sensor.get_instance", return_value=recorder):
        task.on_done(dict.fromkeys(task.revisions, RevisionResult.BOOKED))
    assert entity._revisions == {dt_util.as_utc(_midnight(6)): 3.3}
    await entity.async_will_remove_from_hass()


async def test_old_revisions_are_dropped(hass, coordinator, freezer):
    freezer.move_to(dt.datetime(2026, 5, 20, 0, 5, tzinfo=ROME))
    entity, recorder = await _booking_entity(hass, coordinator, {_midnight(6): 3.1})
    assert recorder.tasks == []
    assert entity._revisions == {}


async def test_revisions_without_recorder_are_dropped(hass, coordinator, freezer):
    freezer.move_to(dt.datetime(2026, 5, 7, 0, 5, tzinfo=ROME))
    entity = _new_entity(hass, coordinator)
    entity._revisions = {dt_util.as_utc(_midnight(6)): 3.1}
    assert "recorder" not in hass.config.components
    with patch("custom_components.ariston.sensor.get_instance") as instance:
        entity._book_revisions()
    instance.assert_not_called()
    assert entity._revisions == {}


@pytest.mark.parametrize(
    "saved", [None, "x", {"2026-05-06T00:00:00": 1.0}, {"x": 1.0}, {5: 1.0},
              {"2026-05-06T00:00:00+02:00": "a"}],
)
async def test_invalid_saved_revisions_are_ignored(hass, coordinator, saved):
    from custom_components.ariston.sensor import _parse_revisions

    assert _parse_revisions(saved) == {}
