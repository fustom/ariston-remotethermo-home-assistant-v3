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
    sum of the period's buckets for the matching `k`/`p` entry instead of
    just the last bucket. For `LAST_DAY` that is today's buckets only.
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


# Hourly buckets kept per consumption type. The cloud only returns 24, but a
# DST fall-back day lasts 25 hours, so the local day can span 25 buckets.
_HISTORY_HOURS = 25
_HISTORY_ATTR = "_ha_hourly_history"
_HOUR = dt.timedelta(hours=1)


def _hourly_history(device, key, buckets: list, current_hour: dt.datetime) -> dict:
    """Return the hourly buckets seen so far, keyed by the UTC start of the hour.

    The cloud replaces `v[]` on every fetch, so a list object we have not
    seen before is fresh data: its buckets are stamped with the hour they
    belong to (`v[23]` = `current_hour`) and merged into the history kept on
    the device. A list we have already seen is not stamped again, so data
    that was fetched before midnight is never attributed to the new day.

    The history lives in memory only: after a restart it starts again from
    the 24 buckets the cloud returns.
    """
    store = getattr(device, _HISTORY_ATTR, None)
    if not isinstance(store, dict):
        store = {}
        try:
            setattr(device, _HISTORY_ATTR, store)
        except AttributeError:
            pass  # Cannot keep history on this object; use this fetch only.
    state = store.setdefault(key, {"source": None, "hours": {}})
    if state["source"] is not buckets:
        hours = state["hours"]
        last = len(buckets) - 1
        for index, value in enumerate(buckets):
            hours[current_hour - (last - index) * _HOUR] = value
        oldest = current_hour - (_HISTORY_HOURS - 1) * _HOUR
        state["hours"] = {h: v for h, v in hours.items() if h >= oldest}
        state["source"] = buckets
    return state["hours"]


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

    For `LAST_DAY` we sum today's buckets only, where "today" is the
    calendar day in Home Assistant's configured time zone, so the value
    pairs cleanly with `last_reset = local midnight` for HA's Energy
    Dashboard (the value drops to ~0 exactly when `last_reset` changes).
    The buckets come from a 25-hour history (see `_hourly_history`), so
    the midnight bucket is still counted in the last hour of a DST
    fall-back day, when it has already left the cloud's 24-hour window.

    For other intervals (week / month / year) we sum the whole `v[]`;
    refining those is left for future work.

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
                now_utc = dt_util.as_utc(local)
                elapsed = now_utc - dt_util.as_utc(midnight)
                current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
                history = _hourly_history(
                    device, consumption_type.value, buckets, current_hour
                )
                # Today is the current hour plus every full hour elapsed
                # since local midnight: up to 25 buckets on a fall-back day.
                count = min(int(elapsed.total_seconds() // 3600) + 1, _HISTORY_HOURS)
                buckets = [history.get(current_hour - i * _HOUR) for i in range(count)]
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
