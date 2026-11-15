"""Helpers to compute energy/consumption sensor values from Ariston cloud data.

Workaround for upstream issue #439. The library getter
`_get_consumption_sequence_last_value` returns only the last bucket of the
`v[]` time-series (e.g. just the last hour of the LAST_DAY interval),
which makes the sensor look like it is reporting a constant ~hourly power
reading instead of an accumulating consumption value. Combined with a
`last_reset` timestamp that the library rewrites to `now - 1h` whenever the
sequences rotate, the HA Energy Dashboard sees frequent fake resets.

This module accesses `device.consumptions_sequences` directly and exposes:

  - `period_total(device, consumption_type, time_interval)` returns the
    sum of `v[]` for the matching `k`/`p` entry, i.e. the full period
    total instead of just the last bucket.
  - `period_last_reset(time_interval)` returns a stable timestamp (in HA's time zone) at
    the start of the period so the HA Energy Dashboard treats one full
    period as a single accumulating window.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from ariston.const import ConsumptionTimeInterval, ConsumptionType
from homeassistant.util import dt as dt_util


def _local_now(now: Optional[dt.datetime]) -> dt.datetime:
    """Return `now` (default: current time) in Home Assistant's time zone.

    Naive datetimes are interpreted as UTC.
    """
    if now is None:
        return dt_util.now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return dt_util.as_local(now)


def period_total(
    device,
    consumption_type: ConsumptionType,
    time_interval: ConsumptionTimeInterval,
    *,
    now: Optional[dt.datetime] = None,
) -> Optional[float]:
    """Sum of bucket values for the given consumption type and period.

    Live API inspection (2026-05-06) showed that `v[]` for `LAST_DAY` is a
    rolling 24-hour series of hourly buckets where `v[23]` is the current
    hour and `v[0]` is 23 hours ago. Summing the whole array therefore
    produces a rolling-24h total, not "today so far", and bleeds yesterday
    into today's reading.

    For `LAST_DAY` we slice to today's portion only, where "today" is the
    calendar day in Home Assistant's configured time zone, so the value
    pairs cleanly with `last_reset = local midnight` for HA's Energy
    Dashboard (the value drops to ~0 exactly when `last_reset` changes). For other intervals (week / month / year) we sum the whole
    `v[]`; refining those is left for future work.

    Returns None if the device has not yet fetched any sequences or the
    expected (k, p) tuple is not present or has empty data.
    """
    sequences = getattr(device, "consumptions_sequences", None)
    if not sequences:
        return None
    for sequence in sequences:
        if (
            sequence.get("k") == consumption_type.value
            and sequence.get("p") == time_interval.value
        ):
            buckets = sequence.get("v") or []
            if not buckets:
                return None
            if time_interval == ConsumptionTimeInterval.LAST_DAY and len(buckets) == 24:
                local = _local_now(now)
                midnight = dt_util.start_of_local_day(local.date())
                # Subtract in UTC: aware datetimes sharing a tzinfo are
                # subtracted by wall-clock, which is wrong across DST.
                elapsed = dt_util.as_utc(local) - dt_util.as_utc(midnight)
                # v[23] = current hour, so today's slice is the last
                # (hours since local midnight + 1) buckets (capped at 24).
                count = min(int(elapsed.total_seconds() // 3600) + 1, 24)
                buckets = buckets[24 - count :]
            total = 0.0
            for value in buckets:
                if value is None:
                    continue
                total += float(value)
            return round(total, 3)
    return None


def period_last_reset(
    time_interval: ConsumptionTimeInterval,
    *,
    now: Optional[dt.datetime] = None,
) -> dt.datetime:
    """Return a stable start-of-period timestamp in HA's time zone.

    The Ariston cloud rolls hourly buckets within `LAST_DAY`, daily
    buckets within `LAST_WEEK`/`LAST_MONTH`, and so on. Anchoring
    `last_reset` to the start of the period (local midnight, week start,
    etc.) means HA sees one reset per period instead of one per cloud
    fetch. HA stores it in UTC, but it is the local instant that must
    match where `period_total` cuts the data.
    """
    today = _local_now(now).date()

    if time_interval == ConsumptionTimeInterval.LAST_WEEK:
        # ISO weekday: Monday = 0
        today = today - dt.timedelta(days=today.weekday())
    elif time_interval == ConsumptionTimeInterval.LAST_MONTH:
        today = today.replace(day=1)
    elif time_interval == ConsumptionTimeInterval.LAST_YEAR:
        today = today.replace(month=1, day=1)

    return dt_util.start_of_local_day(today)
