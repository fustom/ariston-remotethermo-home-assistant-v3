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
  - `previous_day_total(device, consumption_type)` returns yesterday's
    final total, used to close yesterday's cycle right after midnight.
  - `export_history` / `restore_history` save and restore the bucket
    history across Home Assistant restarts.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from ariston.const import (
    ConsumptionTimeInterval,
    ConsumptionType,
    SystemType,
    WheType,
)
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


# Hours kept in memory per consumption type. The cloud only returns 24, but a
# DST fall-back day spans 25 buckets, and yesterday must still be complete
# when the first successful fetch after midnight comes hours late (failed
# polls). 48 hours cover a delay of up to 23 hours.
_RETAINED_HOURS = 48
_HISTORY_ATTR = "_ha_hourly_history"
_HOUR = dt.timedelta(hours=1)


def daily_bucket_hours(device, consumption_type: ConsumptionType) -> int:
    """Return the bucket length of a LAST_DAY sequence."""
    if (
        consumption_type != ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY
        or getattr(device, "system_type", None) != SystemType.VELIS
    ):
        return 1
    model = (getattr(device, "whe_type", None), getattr(device, "whe_model_type", None))
    return 2 if model in ((WheType.Evo2, 4), (WheType.Lydos, 21)) else 1


def _history_state(device, key) -> dict:
    """Return the history kept on the device for one consumption type."""
    store = getattr(device, _HISTORY_ATTR, None)
    if not isinstance(store, dict):
        store = {}
        try:
            setattr(device, _HISTORY_ATTR, store)
        except AttributeError:
            pass  # Cannot keep history on this object; use this fetch only.
    return store.setdefault(key, {"source": None, "hours": {}})


def export_history(device, consumption_type: ConsumptionType) -> dict[str, Any]:
    """Return the history of a consumption type, keyed by ISO bucket start."""
    store = getattr(device, _HISTORY_ATTR, None)
    state = store.get(consumption_type.value) if isinstance(store, dict) else None
    if not state:
        return {}
    return {
        start.isoformat(): value
        for start, value in state["hours"].items()
        if value is not None
    }


def restore_history(
    device,
    consumption_type: ConsumptionType,
    saved: Any,
    *,
    now: Optional[dt.datetime] = None,
) -> None:
    """Merge saved buckets into the history.

    Buckets already in the history come from the cloud after the restart,
    so they win. Buckets older than the retained window are dropped.
    """
    if not isinstance(saved, dict):
        return
    history = _history_state(device, consumption_type.value)["hours"]
    bucket_hours = daily_bucket_hours(device, consumption_type)
    latest = _latest_bucket_start(_local_now(now), bucket_hours)
    oldest = latest - (_RETAINED_HOURS - 1) * _HOUR
    for text, value in saved.items():
        start = dt_util.parse_datetime(text) if isinstance(text, str) else None
        if start is None or start.tzinfo is None or value is None:
            continue
        start = dt_util.as_utc(start)
        if oldest <= start <= latest and _bucket_start(start, bucket_hours) == start:
            try:
                history.setdefault(start, float(value))
            except (TypeError, ValueError):
                continue


def _bucket_history(
    device, key, buckets: list, latest: dt.datetime, step: dt.timedelta
) -> dict:
    """Return the buckets seen so far, keyed by UTC start time.

    The cloud replaces `v[]` on every fetch, so a list object we have not
    seen before is fresh data: its buckets are stamped with their start time
    (`v[23]` = `latest`) and merged into the history kept on
    the device. A list we have already seen is not stamped again, so data
    that was fetched before midnight is never attributed to the new day.
    A null bucket never replaces a known value: the cloud sometimes
    returns nulls for hours it already reported.

    The sensors save it in their restore data (see `export_history`), so
    it survives a restart.
    """
    state = _history_state(device, key)
    if state["source"] is not buckets:
        history = state["hours"]
        last = len(buckets) - 1
        for index, value in enumerate(buckets):
            if value is not None:
                history[latest - (last - index) * step] = value
        oldest = latest - (_RETAINED_HOURS - 1) * _HOUR
        state["hours"] = {
            start: value for start, value in history.items() if start >= oldest
        }
        state["source"] = buckets
    return state["hours"]


def _find_buckets(device, consumption_type, time_interval) -> Optional[list]:
    """Return `v[]` for the matching (k, p) sequence, or None.

    A `v[]` holding only nulls is missing data, not a zero reading.
    """
    for sequence in getattr(device, "consumptions_sequences", None) or []:
        if (
            sequence.get("k") == consumption_type.value
            and sequence.get("p") == time_interval.value
        ):
            buckets = sequence.get("v")
            if not buckets or all(value is None for value in buckets):
                return None
            return buckets
    return None


def _bucket_start(moment: dt.datetime, bucket_hours: int) -> dt.datetime:
    """Return the UTC start of the bucket containing `moment`."""
    hour = dt_util.as_utc(moment).replace(minute=0, second=0, microsecond=0)
    # Issue #552 samples put two-hour boundaries on odd UTC hours.
    # shortcut: The samples cover winter. Verify the grid with summer data.
    if bucket_hours == 2 and hour.hour % 2 == 0:
        return hour - _HOUR
    return hour


def _latest_bucket_start(moment: dt.datetime, bucket_hours: int) -> dt.datetime:
    """Return the start of the latest bucket the cloud includes."""
    current = _bucket_start(moment, bucket_hours)
    return current - 2 * _HOUR if bucket_hours == 2 else current


def _day_bucket_range(
    day: dt.date, bucket_hours: int
) -> tuple[dt.datetime, dt.datetime]:
    """Return the [first, end) buckets of a local day in UTC.

    A bucket that spans midnight belongs to the new day. A bucket that ends
    at midnight belongs to the day that ended.
    """
    start = dt_util.start_of_local_day(day)
    end = dt_util.start_of_local_day(day + dt.timedelta(days=1))
    return _bucket_start(start, bucket_hours), _bucket_start(end, bucket_hours)


def _sum_buckets(
    history: dict,
    start: dt.datetime,
    end: dt.datetime,
    step: dt.timedelta,
    *,
    complete: bool,
) -> Optional[float]:
    """Sum the history buckets in [start, end).

    With `complete`, a missing bucket returns None instead of being skipped.
    """
    total = 0.0
    while start < end:
        value = history.get(start)
        if value is not None:
            total += float(value)
        elif complete:
            return None
        start += step
    return round(total, 3)


def _daily_total(
    device,
    consumption_type: ConsumptionType,
    buckets: list,
    local: dt.datetime,
    bucket_hours: int,
    *,
    previous_day: bool,
) -> Optional[float]:
    """Sum today's available buckets or all of yesterday's buckets."""
    step = bucket_hours * _HOUR
    latest = _latest_bucket_start(local, bucket_hours)
    history = _bucket_history(device, consumption_type.value, buckets, latest, step)
    day = local.date() - dt.timedelta(days=1) if previous_day else local.date()
    start, end = _day_bucket_range(day, bucket_hours)
    if not previous_day:
        end = min(end, latest + step)
    return _sum_buckets(history, start, end, step, complete=previous_day)


def previous_day_total(
    device,
    consumption_type: ConsumptionType,
    *,
    now: Optional[dt.datetime] = None,
) -> Optional[float]:
    """Final total of the local day before `now`, from the bucket history.

    Used to close yesterday's cycle right after midnight: the first fetch of
    the new day can still revise yesterday's last bucket, and that revision
    must be booked under yesterday's `last_reset`, not dropped.

    Returns None when the history does not cover every bucket of that day
    (e.g. after a restart), because a partial sum would understate it.
    """
    buckets = _find_buckets(device, consumption_type, ConsumptionTimeInterval.LAST_DAY)
    if not buckets or len(buckets) != 24:
        return None
    return _daily_total(
        device,
        consumption_type,
        buckets,
        _local_now(now),
        daily_bucket_hours(device, consumption_type),
        previous_day=True,
    )


def period_total(
    device,
    consumption_type: ConsumptionType,
    time_interval: ConsumptionTimeInterval,
    *,
    now: Optional[dt.datetime] = None,
) -> Optional[float]:
    """Sum of bucket values for the given consumption type and period.

    For `LAST_DAY`, the 24 rolling buckets usually end with the current
    hour. For the VELIS models confirmed in #552, DHW total energy ends with
    the last completed two-hour bucket. In both cases we sum the buckets
    assigned to the day in Home Assistant's configured time zone, where
    `last_reset` is local midnight. History keeps today's older buckets
    after they leave the cloud's window on a DST fall-back day.

    For other intervals (week / month / year) we sum the whole `v[]`;
    refining those is left for future work.

    Returns None if the device has not yet fetched any sequences or the
    expected (k, p) tuple is not present or has empty or all-null data.
    """
    buckets = _find_buckets(device, consumption_type, time_interval)
    if not buckets:
        return None
    if time_interval == ConsumptionTimeInterval.LAST_DAY:
        bucket_hours = daily_bucket_hours(device, consumption_type)
        if len(buckets) == 24:
            return _daily_total(
                device,
                consumption_type,
                buckets,
                _local_now(now),
                bucket_hours,
                previous_day=False,
            )
        if bucket_hours == 2:
            return None
    total = 0.0
    for value in buckets:
        if value is None:
            continue
        total += float(value)
    return round(total, 3)


def period_last_reset(
    time_interval: ConsumptionTimeInterval,
    *,
    now: Optional[dt.datetime] = None,
) -> dt.datetime:
    """Return a stable start-of-period timestamp in HA's time zone.

    The Ariston cloud rolls sub-day buckets within `LAST_DAY`, daily
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
