"""Support for Ariston sensors."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import partial
import logging
from typing import Any

from homeassistant.components.recorder.statistics import get_metadata
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.recorder import get_instance
from homeassistant.helpers import restore_state
from homeassistant.helpers.restore_state import (
    ExtraStoredData,
    RestoredExtraData,
    RestoreEntity,
)
from homeassistant.util import dt as dt_util

from .const import ARISTON_SENSOR_TYPES, AristonSensorEntityDescription
from .coordinator import DeviceDataUpdateCoordinator
from .energy import (
    export_history,
    last_bucket_hour,
    previous_day_total,
    restore_history,
)
from .entity import AristonEntity, register_supported_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston sensors from config entry."""
    register_supported_entities(
        hass,
        entry,
        ARISTON_SENSOR_TYPES,
        lambda coordinator, description, _zone=0: (
            AristonDailyConsumptionSensor
            if description.daily_consumption_type is not None
            else AristonSensor
        )(coordinator, description),
        async_add_entities,
    )


class AristonSensor(AristonEntity, SensorEntity):
    """Base class for specific ariston sensors."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSensorEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)

    @property
    def native_value(self):
        """Return value of sensor."""
        return self.entity_description.get_native_value(self)

    @property
    def native_unit_of_measurement(self):
        """Return the nateive unit of measurement."""
        if self.entity_description.get_native_unit_of_measurement is not None:
            return self.entity_description.get_native_unit_of_measurement(self)

        if self.entity_description.native_unit_of_measurement is not None:
            return self.entity_description.native_unit_of_measurement

        return None

    @property
    def last_reset(self) -> datetime | None:
        """Return the time when the sensor was last reset, if any."""
        if self.entity_description.get_last_reset is not None:
            return self.entity_description.get_last_reset(self)

        return None


# Version of the daily consumption calculation, kept in the restore data.
# Missing on the first start after an upgrade from the hourly/rolling values.
DAILY_CONSUMPTION_SCHEME = 2


def _parse_published(saved: Any) -> tuple[float, datetime, float] | None:
    """Parse the saved [value, last_reset, baseline] of the last state."""
    if not isinstance(saved, list) or len(saved) != 3:
        return None
    value, reset, offset = saved
    try:
        parsed = dt_util.parse_datetime(reset) if isinstance(reset, str) else None
        if parsed is None or parsed.tzinfo is None:
            return None
        return (float(value), dt_util.as_utc(parsed), float(offset))
    except (TypeError, ValueError):
        return None


class AristonDailyConsumptionSensor(AristonSensor, RestoreEntity):
    """Today's consumption, reset at local midnight.

    On top of the description's value and `last_reset` it handles two
    Recorder edge cases:

    - Upgrade: the same entity used to report a different quantity, so
      the first new value cannot be compared with the old ones. The
      sensor starts a fresh cycle at the upgrade instant from a baseline
      (today's total at that moment) and reports only what is used after
      it, until the next local midnight. This keeps the existing sum.
      A new sensor has no statistics to keep, so it skips this.
    - Midnight: the first fetch of a new day can still revise yesterday's
      last bucket. Recorder books a state by the time it is written, so a
      state written after midnight would count the revision as today's
      usage. The revision is instead added to yesterday's statistics
      from yesterday's last hour on (`async_adjust_statistics`), and no
      state is written under yesterday's `last_reset`.
      A failed fetch leaves yesterday's cycle open for the next one.
    - Restart: the hourly history and the last published value are kept
      in the restore data, so a restart across midnight still books
      yesterday's revision. The restore data is saved before the
      adjustment is queued, so a crash can lose a revision but never
      book it twice.
    """

    def __init__(self, coordinator, description) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)
        self._baseline: float | None = None
        self._baseline_reset: datetime | None = None
        self._baseline_pending = False
        # Last numeric value, its last_reset and the baseline it excludes.
        self._published: tuple[float, datetime, float] | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the saved state, or start a baseline after an upgrade."""
        await super().async_added_to_hass()
        extra = await self.async_get_last_extra_data()
        data = extra.as_dict() if extra is not None else {}
        if data.get("scheme") == DAILY_CONSUMPTION_SCHEME:
            baseline_reset = data.get("baseline_reset")
            if data.get("baseline") is not None and baseline_reset:
                self._baseline = float(data["baseline"])
                self._baseline_reset = dt_util.parse_datetime(baseline_reset)
            restore_history(
                self.device,
                self.entity_description.daily_consumption_type,
                data.get("history"),
            )
            self._published = _parse_published(data.get("published"))
        elif await self._has_statistics():
            self._baseline_pending = True
        self._update_baseline()
        self._close_previous_day()
        self._remember_published()

    async def _has_statistics(self) -> bool:
        """Whether Recorder holds statistics from before the upgrade.

        Without restore data the entity is either upgraded (it has
        statistics to keep) or new (Recorder takes its first value as the
        baseline, so no migration is needed).
        """
        if "recorder" not in self.hass.config.components:
            return False
        try:
            metadata = await get_instance(self.hass).async_add_executor_job(
                partial(get_metadata, self.hass, statistic_ids={self.entity_id})
            )
        except Exception:  # noqa: BLE001 - a baseline is the safe fallback
            _LOGGER.warning(
                "Could not read statistics of %s, assuming an upgrade",
                self.entity_id,
                exc_info=True,
            )
            return True
        return bool(metadata)

    def _remember_published(self) -> None:
        """Remember the last numeric value and its cycle, for the closing.

        The baseline is kept with it: the baseline can end (at midnight)
        before the closing runs, e.g. when the first fetch has no data.
        """
        value, reset = self._current()
        if value is not None:
            offset = (self._baseline or 0.0) if self._baseline_reset else 0.0
            self._published = (value, dt_util.as_utc(reset), offset)

    @property
    def extra_restore_state_data(self) -> ExtraStoredData | None:
        """Persist the scheme, an active baseline, history and last value."""
        if self._baseline_pending:
            return None  # Still on the old values: migrate on next start.
        data: dict[str, Any] = {"scheme": DAILY_CONSUMPTION_SCHEME}
        if self._baseline_reset is not None:
            data["baseline"] = self._baseline
            data["baseline_reset"] = self._baseline_reset.isoformat()
        data["history"] = export_history(
            self.device, self.entity_description.daily_consumption_type
        )
        if self._published is not None:
            value, reset, offset = self._published
            data["published"] = [value, reset.isoformat(), offset]
        return RestoredExtraData(data)

    def _day_value(self) -> float | None:
        return self.entity_description.get_native_value(self)

    def _day_reset(self) -> datetime:
        return self.entity_description.get_last_reset(self)

    def _update_baseline(self) -> None:
        """Start a pending baseline, or end it when its day is over."""
        if self._baseline_pending:
            value = self._day_value()
            if value is None:
                return  # No data yet: no old value to compare with either.
            self._baseline = value
            self._baseline_reset = dt_util.utcnow().replace(microsecond=0)
            self._baseline_pending = False
        elif (
            self._baseline_reset is not None
            and self._baseline_reset < self._day_reset()
        ):
            self._baseline = None
            self._baseline_reset = None

    def _current(self) -> tuple[float | None, datetime]:
        """Today's value and last_reset (since the baseline, if any)."""
        value = self._day_value()
        if self._baseline_reset is None:
            return value, self._day_reset()
        if value is not None:
            value = round(max(value - (self._baseline or 0.0), 0.0), 3)
        return value, self._baseline_reset

    @property
    def native_value(self):
        """Return today's consumption (since the baseline, if any)."""
        return self._current()[0]

    @property
    def last_reset(self) -> datetime | None:
        """Return local midnight, or the baseline instant."""
        return self._current()[1]

    def _closing_value(self) -> float | None:
        """Yesterday's final total, if it grew since it was last published."""
        if self._published is None:
            return None
        value, reset, offset = self._published
        day_reset = self._day_reset()
        if reset >= day_reset:
            return None
        if dt_util.as_local(reset).date() != (
            dt_util.as_local(day_reset).date() - timedelta(days=1)
        ):
            return None  # Not yesterday's cycle (e.g. a long outage).
        total = previous_day_total(
            self.device, self.entity_description.daily_consumption_type
        )
        if total is None:
            return None
        total = round(total - offset, 3)
        return total if total > value else None

    def _close_previous_day(self) -> None:
        """Book the growth of yesterday's total since it was last published.

        The published value becomes yesterday's final total, so the same
        growth is never booked twice, also after a restart.
        """
        closing = self._closing_value()
        if closing is None or self._published is None:
            return
        value, reset, offset = self._published
        self._published = (closing, reset, offset)
        hour = last_bucket_hour(dt_util.as_local(reset).date())
        # Not started eagerly: the restore data must be saved after the
        # state of this update is written, or it would still hold `value`.
        self.hass.async_create_task(
            self._async_book_revision(round(closing - value, 3), hour),
            eager_start=False,
        )

    async def _async_book_revision(self, amount: float, hour: datetime) -> None:
        """Add `amount` to the statistics from `hour` on.

        The restore data is saved first: if Home Assistant stops before the
        adjustment is stored, the revision is lost, but it is never booked
        a second time on the next start.
        """
        unit = self.native_unit_of_measurement
        if "recorder" not in self.hass.config.components or unit is None:
            return
        await restore_state.async_get(self.hass).async_dump_states()
        get_instance(self.hass).async_adjust_statistics(
            self.entity_id, hour, amount, unit
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Book yesterday's revision, then publish today's value."""
        if not self.coordinator.last_update_success:
            # Unavailable: keep the last published cycle, so the next
            # successful fetch can still close yesterday.
            super()._handle_coordinator_update()
            return
        self._close_previous_day()
        self._update_baseline()
        super()._handle_coordinator_update()
        self._remember_published()
