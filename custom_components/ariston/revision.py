"""Book a revision of yesterday's consumption in Recorder's statistics.

The first fetch after local midnight can still revise yesterday's last
hourly bucket. The revision must land in yesterday's statistics, so it is
written straight into the statistics tables instead of as a state:

- The last 5-minute row of yesterday (start = local midnight - 5 min)
  gets `state` = yesterday's final total and its `sum` grows by the
  difference. The row is created when it is missing, e.g. because the
  sensor was unavailable during yesterday's last hour.
- The hourly row holding that 5-minute row is updated or created the same
  way, and every later row of both tables is shifted by the difference.

All of it runs as one Recorder task, in one transaction, so it is never
interleaved with the statistics compiler and never half applied.

The final total stored in `state` is also the completion marker: a row
that already holds it means the revision is booked, and running the same
revision again changes nothing. The sensor can therefore keep retrying a
revision until Recorder confirms it, also from stale restore data after a
restart, without booking it twice.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime as dt
from enum import StrEnum
import logging
import time
from typing import Any

from homeassistant.components.recorder.db_schema import (
    Statistics,
    StatisticsMeta,
    StatisticsRuns,
    StatisticsShortTerm,
)
from homeassistant.components.recorder.models import process_timestamp
from homeassistant.components.recorder.statistics import (
    STATISTIC_UNIT_TO_UNIT_CONVERTER,
    get_short_term_statistics_run_cache,
)
from homeassistant.components.recorder.tasks import RecorderTask
from homeassistant.components.recorder.util import session_scope
from homeassistant.util import dt as dt_util
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

_LOGGER = logging.getLogger(__name__)

_SHORT_TERM = dt.timedelta(minutes=5)
_HOUR = dt.timedelta(hours=1)
# Values are rounded to 3 decimals before they are published.
_EPSILON = 1e-6
# Seconds: last_reset is stored as a float timestamp.
_RESET_TOLERANCE = 1.0


class RevisionResult(StrEnum):
    """Outcome of booking one revision."""

    BOOKED = "booked"  # Written now.
    UNCHANGED = "unchanged"  # Already booked, or nothing to add.
    SKIPPED = "skipped"  # Cannot be booked (no statistics for that day).
    NOT_READY = "not_ready"  # Yesterday's statistics are not compiled yet.
    FAILED = "failed"  # Database error, retry later.


FINAL_RESULTS = frozenset(
    {RevisionResult.BOOKED, RevisionResult.UNCHANGED, RevisionResult.SKIPPED}
)


@dataclass(frozen=True, slots=True)
class Revision:
    """Yesterday's final total of one sensor, to be booked."""

    statistic_id: str
    last_reset: dt.datetime  # Start of the cycle being closed (UTC).
    total: float  # Final value of that cycle, in `unit`.
    unit: str
    cycle_end: dt.datetime  # Local midnight closing the cycle (UTC).

    @property
    def short_term_start(self) -> dt.datetime:
        """Start of the last 5-minute period of the cycle."""
        return self.cycle_end - _SHORT_TERM

    @property
    def hour_start(self) -> dt.datetime:
        """Start of the hour holding the last 5-minute period."""
        return self.short_term_start.replace(minute=0, second=0, microsecond=0)


def cycle_end(last_reset: dt.datetime) -> dt.datetime:
    """Return the local midnight that ends the day of `last_reset`, in UTC."""
    day = dt_util.as_local(last_reset).date() + dt.timedelta(days=1)
    return dt_util.as_utc(dt_util.start_of_local_day(day))


def _convert(total: float, unit: str, statistic_unit: str | None) -> float | None:
    """Convert `total` to the unit of the statistics, None if impossible."""
    if unit == statistic_unit:
        return total
    converter = STATISTIC_UNIT_TO_UNIT_CONVERTER.get(statistic_unit)
    if converter is None or unit not in converter.VALID_UNITS:
        return None
    return converter.converter_factory(from_unit=unit, to_unit=statistic_unit)(total)


def _latest_row(session: Session, table, metadata_id: int, start: dt.datetime):
    return session.execute(
        select(
            table.id,
            table.start_ts,
            table.state,
            table.sum,
            table.last_reset_ts,
        )
        .where(table.metadata_id == metadata_id, table.start_ts <= start.timestamp())
        .order_by(table.start_ts.desc())
        .limit(1)
    ).first()


def _row_at(session: Session, table, metadata_id: int, start: dt.datetime):
    return session.execute(
        select(table.id, table.last_reset_ts).where(
            table.metadata_id == metadata_id,
            table.start_ts == start.timestamp(),
        )
    ).first()


def _shift_after(
    session: Session, table, metadata_id: int, start: dt.datetime, amount: float
) -> None:
    session.execute(
        update(table)
        .where(table.metadata_id == metadata_id, table.start_ts > start.timestamp())
        .values(sum=table.sum + amount)
        .execution_options(synchronize_session=False)
    )


def _set_row(
    session: Session,
    table,
    metadata_id: int,
    start: dt.datetime,
    row_id: int | None,
    values: dict[str, Any],
) -> None:
    """Update the row `row_id`, or insert one at `start`."""
    if row_id is not None:
        session.execute(
            update(table)
            .where(table.id == row_id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return
    session.add(
        table(
            metadata_id=metadata_id,
            created_ts=time.time(),
            start_ts=start.timestamp(),
            mean=None,
            min=None,
            max=None,
            **values,
        )
    )


def _compiled_until(session: Session) -> dt.datetime | None:
    """Start of the newest compiled 5-minute period, if any."""
    last_run = session.execute(select(func.max(StatisticsRuns.start))).scalar()
    return process_timestamp(last_run) if last_run is not None else None


def book_revision(session: Session, revision: Revision) -> tuple[RevisionResult, int | None]:
    """Book `revision` in the statistics tables.

    Returns the result and the metadata id whose short-term rows changed.
    """
    meta = session.execute(
        select(StatisticsMeta.id, StatisticsMeta.unit_of_measurement).where(
            StatisticsMeta.statistic_id == revision.statistic_id
        )
    ).first()
    if meta is None:
        return RevisionResult.SKIPPED, None
    metadata_id, statistic_unit = meta

    short_start = revision.short_term_start
    hour_start = revision.hour_start
    # Rows must only be added to periods the compiler is done with: it
    # would fail on a duplicate row, and reads the latest row as the base.
    compiled = _compiled_until(session)
    if compiled is None or compiled < hour_start + _HOUR - _SHORT_TERM:
        return RevisionResult.NOT_READY, None

    total = _convert(revision.total, revision.unit, statistic_unit)
    if total is None:
        _LOGGER.warning(
            "Cannot book the revision of %s: unit %s does not convert to %s",
            revision.statistic_id,
            revision.unit,
            statistic_unit,
        )
        return RevisionResult.SKIPPED, None

    # The last short-term row of the cycle is the reference: Recorder
    # continues the sum from it, and its state says what is booked.
    base = _latest_row(session, StatisticsShortTerm, metadata_id, short_start)
    reset_ts = revision.last_reset.timestamp()
    if (
        base is None
        or base.state is None
        or base.last_reset_ts is None
        or abs(base.last_reset_ts - reset_ts) > _RESET_TOLERANCE
    ):
        # Nothing of that cycle reached the statistics: no sum to correct.
        return RevisionResult.SKIPPED, None
    amount = total - base.state
    if amount <= _EPSILON:
        return RevisionResult.UNCHANGED, None

    closing = {
        "state": total,
        "sum": (base.sum or 0.0) + amount,
        "last_reset_ts": reset_ts,
    }
    _set_row(
        session,
        StatisticsShortTerm,
        metadata_id,
        short_start,
        base.id if abs(base.start_ts - short_start.timestamp()) < 1 else None,
        closing,
    )
    _shift_after(session, StatisticsShortTerm, metadata_id, short_start, amount)

    # An hourly row holds the sum of its last short-term row, so the rows
    # from `hour_start` on grow by the same amount.
    hourly = _row_at(session, Statistics, metadata_id, hour_start)
    if hourly is None:
        _set_row(session, Statistics, metadata_id, hour_start, None, closing)
    else:
        values: dict[str, Any] = {"sum": Statistics.sum + amount}
        if (
            hourly.last_reset_ts is not None
            and abs(hourly.last_reset_ts - reset_ts) <= _RESET_TOLERANCE
        ):
            values["state"] = total  # The hour ends in the same cycle.
        _set_row(session, Statistics, metadata_id, hour_start, hourly.id, values)
    _shift_after(session, Statistics, metadata_id, hour_start, amount)
    return RevisionResult.BOOKED, metadata_id


@dataclass(slots=True)
class BookRevisionsTask(RecorderTask):
    """Recorder task booking revisions, then reporting back to the loop."""

    revisions: list[Revision]
    on_done: Callable[[dict[Revision, RevisionResult]], None]

    def run(self, instance) -> None:
        """Book every revision in one transaction, report the results."""
        results = dict.fromkeys(self.revisions, RevisionResult.FAILED)
        changed: set[int] = set()
        try:
            booked = {}
            with session_scope(session=instance.get_session()) as session:
                for revision in self.revisions:
                    result, metadata_id = book_revision(session, revision)
                    booked[revision] = result
                    if metadata_id is not None:
                        changed.add(metadata_id)
            results = booked  # Committed.
        except SQLAlchemyError:
            _LOGGER.warning("Could not book consumption revisions, will retry")
            raise  # Let Recorder recover the database connection.
        except Exception:  # noqa: BLE001 - never stop the Recorder thread
            _LOGGER.exception("Could not book consumption revisions")
        finally:
            if changed:
                # The latest short-term row may be a new one now.
                get_short_term_statistics_run_cache(
                    instance.hass
                ).remove_metadata_ids(changed)
            instance.hass.loop.call_soon_threadsafe(self.on_done, results)
