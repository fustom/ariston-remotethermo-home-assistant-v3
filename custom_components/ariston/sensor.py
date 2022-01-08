"""Support for Ariston sensors."""
from __future__ import annotations

import logging

import homeassistant.util.dt as dt_util

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity

from .entity import AristonEntity
from .ariston import (
    DeviceAttribute,
    PropertyType,
)
from .const import (
    ARISTON_CONSUMPTION_LAST_MONTH_SENSORS_TYPES,
    ARISTON_GAS_CONSUMPTION_LAST_TWO_HOURS_TYPE,
    ARISTON_SENSOR_TYPES,
    DOMAIN,
    AristonSensorEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator, DeviceEnergyUpdateCoordinator


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston sensors from config entry."""
    ariston_sensors = []

    def add_sensor(
        description: AristonSensorEntityDescription,
        sensor_class: AristonSensor
        or AristonGasConsumptionLastTwoHoursSensor
        or AristonEnergyLastMonthSensor,
    ):
        """Add new sensor instance to the sensors list if available"""
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator = (
            hass.data[DOMAIN][entry.unique_id][description.coordinator]
        )
        if coordinator.device.are_device_features_available(
            description.device_features, description.extra_energy_feature
        ):
            ariston_sensors.append(
                sensor_class(
                    coordinator,
                    description,
                )
            )

    for description in ARISTON_SENSOR_TYPES:
        add_sensor(description, AristonSensor)

    for description in ARISTON_GAS_CONSUMPTION_LAST_TWO_HOURS_TYPE:
        add_sensor(description, AristonGasConsumptionLastTwoHoursSensor)

    for description in ARISTON_CONSUMPTION_LAST_MONTH_SENSORS_TYPES:
        add_sensor(description, AristonEnergyLastMonthSensor)

    async_add_entities(ariston_sensors)


class AristonSensor(AristonEntity, SensorEntity):
    """Base class for specific ariston sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator,
        description: AristonSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description)

    @property
    def unique_id(self):
        """Return the unique id."""
        return (
            f"{self.coordinator.device.attributes[DeviceAttribute.GW_ID]}-{self.name}"
        )

    @property
    def native_value(self):
        """Return value of sensor."""
        return self.coordinator.device.get_item_by_id(
            self.entity_description.key, PropertyType.VALUE
        )

    @property
    def native_unit_of_measurement(self):
        """Return the nateive unit of measurement"""
        return self.coordinator.device.get_item_by_id(
            self.entity_description.key, PropertyType.UNIT
        )


class AristonGasConsumptionLastTwoHoursSensor(AristonEntity, SensorEntity):
    """Class for specific ariston energy sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator,
        description: AristonSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description)

        self.current_consumptions_sequences = coordinator.device.consumptions_sequences
        self.reset_datetime = None

    @property
    def unique_id(self):
        """Return the unique id."""
        return (
            f"{self.coordinator.device.attributes[DeviceAttribute.GW_ID]}-{self.name}"
        )

    @property
    def native_value(self):
        """Set last_reset value if sequence is modified. Then return the last two hours value."""
        if (
            self.current_consumptions_sequences
            != self.coordinator.device.consumptions_sequences
        ):
            self.reset_datetime = dt_util.utcnow() - timedelta(hours=1)
            self.current_consumptions_sequences = (
                self.coordinator.device.consumptions_sequences
            )
        return self.coordinator.device.consumptions_sequences[
            int(self.entity_description.key)
        ]["v"][-1]

    @property
    def last_reset(self) -> datetime | None:
        return self.reset_datetime


class AristonEnergyLastMonthSensor(AristonEntity, SensorEntity):
    """Class for specific ariston energy sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator,
        description: AristonSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description)

    @property
    def unique_id(self):
        """Return the unique id."""
        return (
            f"{self.coordinator.device.attributes[DeviceAttribute.GW_ID]}-{self.name}"
        )

    @property
    def native_value(self):
        values = self.entity_description.key.split("|")
        return self.coordinator.device.energy_account["LastMonth"][int(values[0])][
            values[1]
        ]
