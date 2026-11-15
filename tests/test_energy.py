"""Tests for the energy/consumption helpers (issue #439).

"Today" is the calendar day in Home Assistant's time zone. These tests run
with Europe/Rome (UTC+1 in winter, UTC+2 in summer) so that local and UTC
days differ.
"""

import datetime as dt
import zoneinfo
from types import SimpleNamespace

import pytest
from ariston.const import ConsumptionTimeInterval, ConsumptionType
from homeassistant.util import dt as dt_util

from custom_components.ariston.energy import period_last_reset, period_total

ROME = zoneinfo.ZoneInfo("Europe/Rome")
UTC = dt.timezone.utc
DAY = ConsumptionTimeInterval.LAST_DAY
DHW = ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY


@pytest.fixture(autouse=True)
def rome_time_zone():
    """Run every test in Europe/Rome and restore the previous zone."""
    previous = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ROME)
    yield
    dt_util.set_default_time_zone(previous)


def _device(sequences):
    return SimpleNamespace(consumptions_sequences=sequences)


def _day_sequence(values):
    return [{"k": DHW.value, "p": DAY.value, "v": values}]


def _total(values, now):
    return period_total(_device(_day_sequence(values)), DHW, DAY, now=now)


def test_period_total_last_day_slices_to_local_today_only():
    """v[23] is the current hour; only buckets since LOCAL midnight are summed.

    At 14:05 Rome (CEST, 12:05 UTC) today's slice is the last 15 buckets
    (00:00..14:00 local), i.e. v[9:]. A reading from yesterday evening
    (v[8], 23:00 local) must not be included.
    """
    v = [0.0] * 24
    v[8] = 0.45   # yesterday 23:00 local
    v[9] = 0.20   # today 00:00 local (first hour of today)
    v[19] = 0.45  # today 10:00 local
    now = dt.datetime(2026, 5, 6, 14, 5, tzinfo=ROME)
    assert _total(v, now) == pytest.approx(0.65)


def test_period_total_includes_local_night_hours_before_utc_midnight():
    """00:30 Rome in summer is 22:30 UTC the previous day.

    Today (local) has only 1 bucket so far, even though the UTC day started
    22 hours ago. A UTC-based cut would include yesterday's evening.
    """
    v = [0.1] * 24
    v[23] = 0.05
    now = dt.datetime(2026, 5, 6, 22, 30, tzinfo=UTC)  # 00:30 local, 6 May -> 7 May
    assert _total(v, now) == pytest.approx(0.05)


def test_period_total_last_day_at_local_midnight_returns_only_current_hour():
    v = [0.1] * 24
    v[23] = 0.05
    now = dt.datetime(2026, 5, 6, 0, 5, tzinfo=ROME)
    assert _total(v, now) == pytest.approx(0.05)


def test_period_total_last_day_at_2300_local_sums_full_array():
    now = dt.datetime(2026, 5, 6, 23, 59, tzinfo=ROME)
    assert _total([0.1] * 24, now) == pytest.approx(2.4)


def test_period_total_handles_spring_forward_day():
    """On 2026-03-29 Rome skips 02:00->03:00, so the day has 23 hours.

    At 12:30 CEST (10:30 UTC) 11 local hours have elapsed since midnight
    (00:00 CET = 23:00 UTC), so 12 buckets belong to today.
    """
    v = [0.0] * 24
    v[12] = 1.0   # oldest of today's 12 buckets (v[12:])
    v[11] = 5.0   # one earlier -> yesterday
    now = dt.datetime(2026, 3, 29, 12, 30, tzinfo=ROME)
    assert _total(v, now) == pytest.approx(1.0)


def test_period_total_handles_fall_back_day():
    """On 2026-10-25 Rome repeats 02:00-03:00, so the day has 25 hours.

    At 12:30 CET (11:30 UTC) 13 hours have elapsed since midnight
    (00:00 CEST = 22:00 UTC), so 14 buckets belong to today.
    """
    v = [0.0] * 24
    v[10] = 1.0   # 14th bucket from the end -> still today
    v[9] = 5.0    # one earlier -> yesterday
    now = dt.datetime(2026, 10, 25, 12, 30, tzinfo=ROME)
    assert _total(v, now) == pytest.approx(1.0)


def test_value_and_last_reset_change_together_at_local_midnight():
    """HA needs the value to restart exactly when last_reset moves."""
    before = dt.datetime(2026, 5, 6, 23, 59, tzinfo=ROME)
    after = dt.datetime(2026, 5, 7, 0, 1, tzinfo=ROME)
    v_before = [0.1] * 24
    v_after = [0.1] * 23 + [0.02]  # buckets rolled by one hour
    assert _total(v_before, before) == pytest.approx(2.4)
    assert _total(v_after, after) == pytest.approx(0.02)
    assert period_last_reset(DAY, now=before) != period_last_reset(DAY, now=after)


def test_period_total_non_last_day_sums_full_array():
    """Week/month/year intervals are summed in full (no slicing yet)."""
    sequences = [
        {
            "k": ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.value,
            "p": ConsumptionTimeInterval.LAST_WEEK.value,
            "v": [None, 1.2, None, 0.8],
        }
    ]
    total = period_total(
        _device(sequences),
        ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY,
        ConsumptionTimeInterval.LAST_WEEK,
    )
    assert total == pytest.approx(2.0)


def test_period_total_last_day_short_array_falls_back_to_full_sum():
    """If for some reason v[] isn't 24 elements, do not slice (defensive)."""
    sequences = [
        {
            "k": ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY.value,
            "p": ConsumptionTimeInterval.LAST_DAY.value,
            "v": [0.1, 0.2, 0.3],
        }
    ]
    now = dt.datetime(2026, 5, 6, 14, 0, 0, tzinfo=dt.timezone.utc)
    total = period_total(
        _device(sequences),
        ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
        ConsumptionTimeInterval.LAST_DAY,
        now=now,
    )
    assert total == pytest.approx(0.6)


def test_period_total_returns_none_when_no_sequences():
    assert (
        period_total(
            _device([]),
            ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
            ConsumptionTimeInterval.LAST_DAY,
        )
        is None
    )


def test_period_total_returns_none_when_no_match():
    sequences = [
        {
            "k": ConsumptionType.CENTRAL_HEATING_GAS.value,
            "p": ConsumptionTimeInterval.LAST_DAY.value,
            "v": [1.0, 2.0],
        }
    ]
    assert (
        period_total(
            _device(sequences),
            ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
            ConsumptionTimeInterval.LAST_DAY,
        )
        is None
    )


def test_period_total_returns_none_for_empty_buckets():
    sequences = [
        {
            "k": ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY.value,
            "p": ConsumptionTimeInterval.LAST_DAY.value,
            "v": [],
        }
    ]
    assert (
        period_total(
            _device(sequences),
            ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
            ConsumptionTimeInterval.LAST_DAY,
        )
        is None
    )


def test_last_reset_day_is_local_midnight():
    now = dt.datetime(2026, 5, 6, 14, 32, 17, tzinfo=ROME)
    reset = period_last_reset(DAY, now=now)
    assert reset == dt.datetime(2026, 5, 6, 0, 0, tzinfo=ROME)
    assert dt_util.as_utc(reset) == dt.datetime(2026, 5, 5, 22, 0, tzinfo=UTC)


def test_last_reset_day_follows_local_date_not_utc_date():
    """23:30 UTC on 6 May is already 7 May in Rome."""
    now = dt.datetime(2026, 5, 6, 23, 30, tzinfo=UTC)
    assert period_last_reset(DAY, now=now) == dt.datetime(2026, 5, 7, 0, 0, tzinfo=ROME)


def test_last_reset_is_stable_within_the_day():
    a = period_last_reset(DAY, now=dt.datetime(2026, 5, 6, 0, 1, tzinfo=ROME))
    b = period_last_reset(DAY, now=dt.datetime(2026, 5, 6, 23, 59, tzinfo=ROME))
    assert a == b


def test_last_reset_week_is_monday_local_midnight():
    # 2026-05-06 is a Wednesday -> Monday is 2026-05-04
    now = dt.datetime(2026, 5, 6, 14, 32, 17, tzinfo=ROME)
    reset = period_last_reset(ConsumptionTimeInterval.LAST_WEEK, now=now)
    assert reset == dt.datetime(2026, 5, 4, 0, 0, tzinfo=ROME)


def test_last_reset_month_is_first_of_month_local_midnight():
    now = dt.datetime(2026, 5, 6, 14, 32, 17, tzinfo=ROME)
    reset = period_last_reset(ConsumptionTimeInterval.LAST_MONTH, now=now)
    assert reset == dt.datetime(2026, 5, 1, 0, 0, tzinfo=ROME)


def test_last_reset_year_is_first_of_year_local_midnight():
    now = dt.datetime(2026, 5, 6, 14, 32, 17, tzinfo=ROME)
    reset = period_last_reset(ConsumptionTimeInterval.LAST_YEAR, now=now)
    assert reset == dt.datetime(2026, 1, 1, 0, 0, tzinfo=ROME)


def test_last_reset_normalizes_naive_input_as_utc():
    # 23:30 UTC naive -> 01:30 on 7 May in Rome
    now = dt.datetime(2026, 5, 6, 23, 30)
    reset = period_last_reset(DAY, now=now)
    assert reset == dt.datetime(2026, 5, 7, 0, 0, tzinfo=ROME)
    assert reset.tzinfo is not None
