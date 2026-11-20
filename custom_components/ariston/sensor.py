"""Support for Ariston sensors."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.restore_state import (
    ExtraStoredData,
    RestoredExtraData,
    RestoreEntity,
)
from homeassistant.util import dt as dt_util

from .const import ARISTON_SENSOR_TYPES, AristonSensorEntityDescription
from .coordinator import DeviceDataUpdateCoordinator
from .energy import previous_day_total
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


class AristonDailyConsumptionSensor(AristonSensor, RestoreEntity):
    """Today's consumption, reset at local midnight.

    On top of the description's value and `last_reset` it handles two
    Recorder edge cases:

    - Upgrade: the same entity used to report a different quantity, so
      the first new value cannot be compared with the old ones. The
      sensor starts a fresh cycle at the upgrade instant from a baseline
      (today's total at that moment) and reports only what is used after
      it, until the next local midnight. This keeps the existing sum.
    - Midnight: the first fetch of a new day can still revise yesterday's
      last bucket. Before the new `last_reset` is published, yesterday's
      final total is written under the old one so Recorder books it.
    """

    def __init__(self, coordinator, description) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)
        self._baseline: float | None = None
        self._baseline_reset: datetime | None = None
        self._baseline_pending = False
        self._published: tuple[float | None, datetime | None] | None = None
        self._override: tuple[float, datetime] | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the baseline, or start one after an upgrade."""
        await super().async_added_to_hass()
        extra = await self.async_get_last_extra_data()
        data = extra.as_dict() if extra is not None else {}
        if data.get("scheme") == DAILY_CONSUMPTION_SCHEME:
            baseline_reset = data.get("baseline_reset")
            if data.get("baseline") is not None and baseline_reset:
                self._baseline = float(data["baseline"])
                self._baseline_reset = dt_util.parse_datetime(baseline_reset)
        else:
            self._baseline_pending = True
        self._update_baseline()
        self._published = (self.native_value, self.last_reset)

    @property
    def extra_restore_state_data(self) -> ExtraStoredData | None:
        """Persist the scheme version and an active baseline."""
        if self._baseline_pending:
            return None  # Still on the old values: migrate on next start.
        data: dict[str, Any] = {"scheme": DAILY_CONSUMPTION_SCHEME}
        if self._baseline_reset is not None:
            data["baseline"] = self._baseline
            data["baseline_reset"] = self._baseline_reset.isoformat()
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

    @property
    def native_value(self):
        """Return today's consumption (since the baseline, if any)."""
        if self._override is not None:
            return self._override[0]
        value = self._day_value()
        if value is None or self._baseline_reset is None:
            return value
        return round(max(value - (self._baseline or 0.0), 0.0), 3)

    @property
    def last_reset(self) -> datetime | None:
        """Return local midnight, or the baseline instant after an upgrade."""
        if self._override is not None:
            return self._override[1]
        return self._baseline_reset or self._day_reset()

    def _closing_value(self) -> float | None:
        """Yesterday's final total, if it grew since it was last published."""
        if self._published is None:
            return None
        value, reset = self._published
        day_reset = self._day_reset()
        if value is None or reset is None or reset >= day_reset:
            return None
        total = previous_day_total(
            self.device, self.entity_description.daily_consumption_type
        )
        if total is None:
            return None
        if reset == self._baseline_reset:
            total -= self._baseline or 0.0
        elif dt_util.as_local(reset).date() != (
            dt_util.as_local(day_reset).date() - timedelta(days=1)
        ):
            return None  # Not yesterday's cycle (e.g. a long outage).
        total = round(total, 3)
        return total if total > value else None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Close yesterday's cycle, then publish today's value."""
        closing = self._closing_value()
        if closing is not None and self._published is not None:
            self._override = (closing, self._published[1])
            try:
                self.async_write_ha_state()
            finally:
                self._override = None
        self._update_baseline()
        super()._handle_coordinator_update()
        self._published = (self.native_value, self.last_reset)
