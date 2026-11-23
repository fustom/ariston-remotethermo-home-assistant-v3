"""Booking yesterday's revision in Recorder's statistics tables (PR #532).

Runs against Recorder's real schema in an in-memory SQLite database.
Europe/Rome, 6 May 2026: local midnight is 22:00 UTC, so yesterday's last
5-minute row starts at 21:55 UTC and its hour at 21:00 UTC.
"""

import asyncio
import datetime as dt
from types import SimpleNamespace
import zoneinfo

import pytest
from homeassistant.components.recorder.db_schema import (
    Base,
    Statistics,
    StatisticsMeta,
    StatisticsRuns,
    StatisticsShortTerm,
)
from homeassistant.components.recorder.statistics import (
    get_short_term_statistics_run_cache,
)
from homeassistant.util import dt as dt_util
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from custom_components.ariston.revision import (
    BookRevisionsTask,
    Revision,
    RevisionResult,
    book_revision,
    cycle_end,
)

ROME = zoneinfo.ZoneInfo("Europe/Rome")
UTC = dt.UTC
ENTITY = "sensor.dhw_total"
YESTERDAY = dt.datetime(2026, 5, 6, tzinfo=ROME)
TODAY = dt.datetime(2026, 5, 7, tzinfo=ROME)


@pytest.fixture(autouse=True)
async def rome_time_zone(hass):
    await hass.config.async_set_time_zone("Europe/Rome")


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, future=True)
    engine.dispose()


def _utc(hour, minute=0, day=6):
    return dt.datetime(2026, 5, day, hour, minute, tzinfo=UTC)


def _meta(session, unit="kWh"):
    meta = StatisticsMeta(
        statistic_id=ENTITY,
        source="recorder",
        unit_of_measurement=unit,
        has_sum=True,
        name=None,
    )
    session.add(meta)
    session.flush()
    return meta.id


def _row(session, table, metadata_id, start, state, total, reset):
    session.add(
        table(
            metadata_id=metadata_id,
            created_ts=0.0,
            start_ts=start.timestamp(),
            state=state,
            sum=total,
            last_reset_ts=dt_util.as_utc(reset).timestamp(),
        )
    )


def _compiled(session, until):
    session.add(StatisticsRuns(start=until))


def _rows(session, table):
    return [
        (
            dt.datetime.fromtimestamp(row.start_ts, UTC),
            pytest.approx(row.state),
            pytest.approx(row.sum),
            dt.datetime.fromtimestamp(row.last_reset_ts, UTC),
        )
        for row in session.execute(select(table).order_by(table.start_ts)).scalars()
    ]


def _revision(total=3.1, unit="kWh", reset=YESTERDAY):
    return Revision(ENTITY, dt_util.as_utc(reset), total, unit, cycle_end(reset))


def _book(db, revision=None):
    with db() as session:
        result = book_revision(session, revision or _revision())
        session.commit()
    return result


Y = dt_util.as_utc(YESTERDAY)
T = dt_util.as_utc(TODAY)


def test_cycle_end_and_periods():
    revision = _revision()
    assert revision.cycle_end == _utc(22)
    assert revision.short_term_start == _utc(21, 55)
    assert revision.hour_start == _utc(21)


async def test_cycle_end_with_fractional_offset(hass):
    await hass.config.async_set_time_zone("Asia/Kolkata")
    kolkata = zoneinfo.ZoneInfo("Asia/Kolkata")
    revision = _revision(reset=dt.datetime(2026, 5, 6, tzinfo=kolkata))
    assert revision.cycle_end == _utc(18, 30)
    assert revision.short_term_start == _utc(18, 25)
    assert revision.hour_start == _utc(18)


def test_revision_updates_the_last_rows_and_shifts_the_later_ones(db):
    with db() as session:
        mid = _meta(session)
        _row(session, StatisticsShortTerm, mid, _utc(21, 50), 2.5, 10.0, Y)
        _row(session, StatisticsShortTerm, mid, _utc(21, 55), 2.5, 10.0, Y)
        _row(session, StatisticsShortTerm, mid, _utc(22), 0.05, 10.05, T)
        _row(session, Statistics, mid, _utc(21), 2.5, 10.0, Y)
        _row(session, Statistics, mid, _utc(22), 0.05, 10.05, T)
        _compiled(session, _utc(22, 55))
        session.commit()

    assert _book(db) == (RevisionResult.BOOKED, mid)

    with db() as session:
        assert _rows(session, StatisticsShortTerm) == [
            (_utc(21, 50), 2.5, 10.0, Y),
            (_utc(21, 55), 3.1, 10.6, Y),
            (_utc(22), 0.05, 10.65, T),
        ]
        assert _rows(session, Statistics) == [
            (_utc(21), 3.1, 10.6, Y),
            (_utc(22), 0.05, 10.65, T),
        ]


def test_same_revision_twice_is_booked_once(db):
    """Reviewer's case: stale restore data queues the same 0.6 again."""
    with db() as session:
        mid = _meta(session)
        _row(session, StatisticsShortTerm, mid, _utc(21, 55), 2.5, 10.0, Y)
        _row(session, Statistics, mid, _utc(21), 2.5, 10.0, Y)
        _compiled(session, _utc(22))
        session.commit()

    assert _book(db)[0] is RevisionResult.BOOKED
    assert _book(db)[0] is RevisionResult.UNCHANGED
    # A later, larger revision of the same day adds only the difference.
    assert _book(db, _revision(3.3))[0] is RevisionResult.BOOKED

    with db() as session:
        assert _rows(session, StatisticsShortTerm) == [
            (_utc(21, 55), 3.3, 10.8, Y)
        ]
        assert _rows(session, Statistics) == [(_utc(21), 3.3, 10.8, Y)]


def test_missing_last_hour_before_todays_rows(db):
    """Reviewer's case: unavailable in yesterday's last hour, job runs first.

    The rows of the missing hour are created, so the next compile continues
    from yesterday's final total instead of dropping the correction.
    """
    with db() as session:
        mid = _meta(session)
        _row(session, StatisticsShortTerm, mid, _utc(20, 55), 2.5, 10.0, Y)
        _row(session, Statistics, mid, _utc(20), 2.5, 10.0, Y)
        _compiled(session, _utc(22))
        session.commit()

    assert _book(db, _revision(3.4))[0] is RevisionResult.BOOKED

    with db() as session:
        assert _rows(session, StatisticsShortTerm) == [
            (_utc(20, 55), 2.5, 10.0, Y),
            (_utc(21, 55), 3.4, 10.9, Y),
        ]
        assert _rows(session, Statistics) == [
            (_utc(20), 2.5, 10.0, Y),
            (_utc(21), 3.4, 10.9, Y),
        ]


def test_missing_last_hour_after_todays_rows(db):
    """Reviewer's case: today's rows exist, the correction stays in yesterday."""
    with db() as session:
        mid = _meta(session)
        _row(session, StatisticsShortTerm, mid, _utc(20, 55), 2.5, 10.0, Y)
        _row(session, StatisticsShortTerm, mid, _utc(22, 5), 0.05, 10.05, T)
        _row(session, Statistics, mid, _utc(20), 2.5, 10.0, Y)
        _row(session, Statistics, mid, _utc(22), 0.05, 10.05, T)
        _compiled(session, _utc(22, 55))
        session.commit()

    assert _book(db, _revision(3.4))[0] is RevisionResult.BOOKED

    with db() as session:
        assert _rows(session, Statistics) == [
            (_utc(20), 2.5, 10.0, Y),
            (_utc(21), 3.4, 10.9, Y),  # yesterday: +0.9
            (_utc(22), 0.05, 10.95, T),  # today: still +0.05
        ]
        assert _rows(session, StatisticsShortTerm)[-1] == (
            _utc(22, 5), 0.05, 10.95, T
        )


def test_hour_spanning_midnight_keeps_todays_state(db, hass):
    """Asia/Kolkata: the 18:00 UTC hour ends in today's cycle."""
    kolkata = zoneinfo.ZoneInfo("Asia/Kolkata")
    reset = dt.datetime(2026, 5, 6, tzinfo=kolkata)
    today = dt.datetime(2026, 5, 7, tzinfo=kolkata)
    with db() as session:
        mid = _meta(session)
        _row(session, StatisticsShortTerm, mid, _utc(18, 25), 2.5, 10.0, reset)
        _row(session, StatisticsShortTerm, mid, _utc(18, 55), 0.05, 10.05, today)
        _row(session, Statistics, mid, _utc(18), 0.05, 10.05, today)
        _compiled(session, _utc(18, 55))
        session.commit()

    revision = Revision(
        ENTITY, dt_util.as_utc(reset), 3.1, "kWh", _utc(18, 30)
    )
    assert _book(db, revision)[0] is RevisionResult.BOOKED

    with db() as session:
        assert _rows(session, Statistics) == [
            (_utc(18), 0.05, 10.65, dt_util.as_utc(today))
        ]
        assert _rows(session, StatisticsShortTerm) == [
            (_utc(18, 25), 3.1, 10.6, dt_util.as_utc(reset)),
            (_utc(18, 55), 0.05, 10.65, dt_util.as_utc(today)),
        ]


def test_not_ready_until_first_new_day_period_is_compiled(db):
    with db() as session:
        mid = _meta(session)
        _row(session, StatisticsShortTerm, mid, _utc(21, 50), 2.5, 10.0, Y)
        _compiled(session, _utc(21, 50))
        session.commit()
    assert _book(db) == (RevisionResult.NOT_READY, None)

    # Compiling yesterday's final period is not enough: the first new-day
    # period must also compile before the correction is booked.
    with db() as session:
        _compiled(session, _utc(21, 55))
        session.commit()
    assert _book(db) == (RevisionResult.NOT_READY, None)

    with db() as session:
        _row(session, StatisticsShortTerm, mid, _utc(22), 0.05, 10.05, T)
        _compiled(session, _utc(22))
        session.commit()
    assert _book(db)[0] is RevisionResult.BOOKED

    with db() as session:
        assert _rows(session, StatisticsShortTerm) == [
            (_utc(21, 50), 2.5, 10.0, Y),
            (_utc(21, 55), 3.1, 10.6, Y),
            (_utc(22), 0.05, 10.65, T),
        ]


def test_not_ready_without_any_compiled_run(db):
    with db() as session:
        _meta(session)
        session.commit()
    assert _book(db) == (RevisionResult.NOT_READY, None)


def test_skipped_without_statistics(db):
    assert _book(db) == (RevisionResult.SKIPPED, None)


@pytest.mark.parametrize("case", ["no rows", "older cycle", "no state"])
def test_skipped_when_the_cycle_is_not_in_the_statistics(db, case):
    with db() as session:
        mid = _meta(session)
        if case == "older cycle":
            older = dt_util.as_utc(dt.datetime(2026, 5, 5, tzinfo=ROME))
            _row(session, StatisticsShortTerm, mid, _utc(20), 1.0, 9.0, older)
        elif case == "no state":
            _row(session, StatisticsShortTerm, mid, _utc(20), None, 9.0, Y)
        _compiled(session, _utc(22))
        session.commit()
    assert _book(db) == (RevisionResult.SKIPPED, None)


def test_revision_is_converted_to_the_statistics_unit(db):
    with db() as session:
        mid = _meta(session, unit="Wh")
        _row(session, StatisticsShortTerm, mid, _utc(21, 55), 2500, 10000, Y)
        _row(session, Statistics, mid, _utc(21), 2500, 10000, Y)
        _compiled(session, _utc(22))
        session.commit()

    assert _book(db)[0] is RevisionResult.BOOKED
    with db() as session:
        assert _rows(session, Statistics) == [(_utc(21), 3100, 10600, Y)]


def test_unconvertible_unit_is_skipped(db):
    with db() as session:
        _meta(session, unit="m³")
        _compiled(session, _utc(22))
        session.commit()
    assert _book(db) == (RevisionResult.SKIPPED, None)


async def _run(hass, db, revisions, session_factory=None):
    results = []
    instance = SimpleNamespace(get_session=session_factory or db, hass=hass)
    task = BookRevisionsTask(revisions, results.append)
    await hass.async_add_executor_job(task.run, instance)
    await asyncio.sleep(0)
    return results


async def test_task_reports_results_and_refreshes_the_run_cache(hass, db):
    with db() as session:
        mid = _meta(session)
        _row(session, StatisticsShortTerm, mid, _utc(20, 55), 2.5, 10.0, Y)
        _compiled(session, _utc(22))
        session.commit()
    cache = get_short_term_statistics_run_cache(hass)
    cache.set_latest_id_for_metadata_id(mid, 1)

    revision = _revision()
    other = _revision(reset=dt.datetime(2026, 5, 4, tzinfo=ROME))
    assert await _run(hass, db, [revision, other]) == [
        {revision: RevisionResult.BOOKED, other: RevisionResult.SKIPPED}
    ]
    # The new 21:55 row is the latest now: Recorder must look it up again.
    assert cache.get_latest_ids({mid}) == {}


async def test_task_reports_a_database_error(hass, db):
    def broken():
        raise OperationalError("SELECT", {}, Exception("locked"))

    revision = _revision()
    results = []
    task = BookRevisionsTask([revision], results.append)
    instance = SimpleNamespace(get_session=broken, hass=hass)
    with pytest.raises(OperationalError):  # Recorder recovers the connection.
        await hass.async_add_executor_job(task.run, instance)
    await asyncio.sleep(0)
    assert results == [{revision: RevisionResult.FAILED}]


async def test_task_never_raises_other_errors(hass, db):
    def broken():
        raise RuntimeError("bug")

    revision = _revision()
    assert await _run(hass, db, [revision], session_factory=broken) == [
        {revision: RevisionResult.FAILED}
    ]
