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
  - `export_history` / `restore_history` save and restore the hourly
    history across Home Assistant restarts.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

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


# Hours kept in memory per consumption type. The cloud only returns 24, but a
# DST fall-back day spans 25 buckets, and yesterday must still be complete
# when the first successful fetch after midnight comes hours late (failed
# polls). 48 hours cover a delay of up to 23 hours.
_RETAINED_HOURS = 48
_HISTORY_ATTR = "_ha_hourly_history"
_HOUR = dt.timedelta(hours=1)


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
    """Return the hourly history of a consumption type, keyed by ISO hour."""
    store = getattr(device, _HISTORY_ATTR, None)
    state = store.get(consumption_type.value) if isinstance(store, dict) else None
    if not state:
        return {}
    return {
        hour.isoformat(): value
        for hour, value in state["hours"].items()
        if value is not None
    }


def restore_history(
    device,
    consumption_type: ConsumptionType,
    saved: Any,
    *,
    now: Optional[dt.datetime] = None,
) -> None:
    """Merge saved hourly buckets into the history.

    Buckets already in the history come from the cloud after the restart,
    so they win. Buckets older than the retained window are dropped.
    """
    if not isinstance(saved, dict):
        return
    hours = _history_state(device, consumption_type.value)["hours"]
    oldest = _utc_hour(_local_now(now)) - (_RETAINED_HOURS - 1) * _HOUR
    for text, value in saved.items():
        hour = dt_util.parse_datetime(text) if isinstance(text, str) else None
        if hour is None or hour.tzinfo is None or value is None:
            continue
        hour = dt_util.as_utc(hour)
        if hour >= oldest:
            try:
                hours.setdefault(hour, float(value))
            except (TypeError, ValueError):
                continue


def _hourly_history(device, key, buckets: list, current_hour: dt.datetime) -> dict:
    """Return the hourly buckets seen so far, keyed by the UTC start of the hour.

    The cloud replaces `v[]` on every fetch, so a list object we have not
    seen before is fresh data: its buckets are stamped with the hour they
    belong to (`v[23]` = `current_hour`) and merged into the history kept on
    the device. A list we have already seen is not stamped again, so data
    that was fetched before midnight is never attributed to the new day.
    A null bucket never replaces a known value: the cloud sometimes
    returns nulls for hours it already reported.

    The sensors save it in their restore data (see `export_history`), so
    it survives a restart.
    """
    state = _history_state(device, key)
    if state["source"] is not buckets:
        hours = state["hours"]
        last = len(buckets) - 1
        for index, value in enumerate(buckets):
            if value is not None:
                hours[current_hour - (last - index) * _HOUR] = value
        oldest = current_hour - (_RETAINED_HOURS - 1) * _HOUR
        state["hours"] = {h: v for h, v in hours.items() if h >= oldest}
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


def _utc_hour(moment: dt.datetime) -> dt.datetime:
    """Return the start of the whole UTC hour containing `moment`."""
    return dt_util.as_utc(moment).replace(minute=0, second=0, microsecond=0)


def _day_bucket_range(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Return the [first, end) bucket hours, in UTC, of a local day.

    History keys are whole UTC hours. Where local midnight is not on a
    whole UTC hour (e.g. Asia/Kolkata, UTC+5:30), one bucket spans it: that
    bucket belongs to the new day. Storing and lookup both go through this
    function, so every bucket belongs to exactly one local day. A DST day
    spans 23 or 25 buckets.
    """
    start = _utc_hour(dt_util.start_of_local_day(day))
    end = _utc_hour(dt_util.start_of_local_day(day + dt.timedelta(days=1)))
    return start, end


def _sum_hours(
    history: dict, start: dt.datetime, end: dt.datetime, *, complete: bool
) -> Optional[float]:
    """Sum the history buckets in [start, end).

    With `complete`, a missing bucket returns None instead of being skipped.
    """
    total = 0.0
    hour = start
    while hour < end:
        value = history.get(hour)
        if value is not None:
            total += float(value)
        elif complete:
            return None
        hour += _HOUR
    return round(total, 3)


def previous_day_total(
    device,
    consumption_type: ConsumptionType,
    *,
    now: Optional[dt.datetime] = None,
) -> Optional[float]:
    """Final total of the local day before `now`, from the hourly history.

    Used to close yesterday's cycle right after midnight: the first fetch of
    the new day can still revise yesterday's last bucket, and that revision
    must be booked under yesterday's `last_reset`, not dropped.

    Returns None when the history does not cover every hour of that day
    (e.g. after a restart), because a partial sum would understate it.
    """
    buckets = _find_buckets(device, consumption_type, ConsumptionTimeInterval.LAST_DAY)
    if not buckets or len(buckets) != 24:
        return None
    local = _local_now(now)
    history = _hourly_history(
        device, consumption_type.value, buckets, _utc_hour(local)
    )
    start, end = _day_bucket_range(local.date() - dt.timedelta(days=1))
    return _sum_hours(history, start, end, complete=True)


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
    The buckets come from the hourly history (see `_hourly_history`), so
    the midnight bucket is still counted in the last hour of a DST
    fall-back day, when it has already left the cloud's 24-hour window.
    Which buckets make up a day is decided by `_day_bucket_range`.

    For other intervals (week / month / year) we sum the whole `v[]`;
    refining those is left for future work.

    Returns None if the device has not yet fetched any sequences or the
    expected (k, p) tuple is not present or has empty or all-null data.
    """
    buckets = _find_buckets(device, consumption_type, time_interval)
    if not buckets:
        return None
    if time_interval == ConsumptionTimeInterval.LAST_DAY and len(buckets) == 24:
        local = _local_now(now)
        current_hour = _utc_hour(local)
        history = _hourly_history(device, consumption_type.value, buckets, current_hour)
        # Today's buckets up to the current one. Where midnight is not on a
        # whole UTC hour, the current bucket can already belong to tomorrow.
        start, end = _day_bucket_range(local.date())
        return _sum_hours(
            history, start, min(end, current_hour + _HOUR), complete=False
        )
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
