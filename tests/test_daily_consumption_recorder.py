"""The upgrade check of the daily consumption sensors against a real Recorder.

Kept apart from test_daily_consumption_sensor.py: its autouse time zone
fixture starts `hass` before `recorder_mock` can set the Recorder up.
"""

import datetime as dt

from homeassistant.components.recorder.models import (
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.util import dt as dt_util
from pytest_homeassistant.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.ariston.const import ARISTON_SENSOR_TYPES
from custom_components.ariston.sensor import AristonDailyConsumptionSensor


async def test_has_statistics_with_a_real_recorder(recorder_mock, hass, coordinator):
    description = next(d for d in ARISTON_SENSOR_TYPES if d.daily_consumption_type)
    entity = AristonDailyConsumptionSensor(coordinator, description)
    entity.hass = hass
    entity.entity_id = "sensor.dhw_total"
    assert await entity._has_statistics() is False

    metadata = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=None,
        source="recorder",
        statistic_id="sensor.dhw_total",
        unit_class="energy",
        unit_of_measurement="kWh",
    )
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    async_import_statistics(
        hass, metadata, [{"start": start - dt.timedelta(hours=2), "sum": 1.0}]
    )
    await async_wait_recording_done(hass)

    assert await entity._has_statistics() is True
