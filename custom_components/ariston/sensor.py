"""Support for Ariston sensors."""
from __future__ import annotations

import logging
import homeassistant.util.dt as dt_util

from datetime import datetime, timedelta

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)

from .ariston import (
    DeviceAttribute,
    DeviceFeatures,
    PropertyType,
)
from .const import (
    ARISTON_HEATING_CONSUMPTION_LAST_MONTH_SENSORS_TYPES,
    ARISTON_WATER_CONSUMPTION_LAST_MONTH_SENSORS_TYPES,
    ARISTON_GAS_CONSUMPTION_HEATING_LAST_TWO_HOURS_TYPE,
    ARISTON_GAS_CONSUMPTION_WATER_LAST_TWO_HOURS_TYPE,
    ARISTON_SENSOR_TYPES,
    COORDINATOR,
    DOMAIN,
    ENERGY_COORDINATOR,
)
from .coordinator import DeviceDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston sensors from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
        COORDINATOR
    ]

    ariston_sensors: list[AristonSensor] = []
    for description in ARISTON_SENSOR_TYPES:
        ariston_sensors.append(
            AristonSensor(
                coordinator,
                description,
            )
        )

    if coordinator.device.features[DeviceFeatures.HAS_METERING]:
        energy_coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][
            entry.unique_id
        ][ENERGY_COORDINATOR]
        ariston_sensors.append(
            AristonGasConsumptionLastTwoHours(
                energy_coordinator, ARISTON_GAS_CONSUMPTION_HEATING_LAST_TWO_HOURS_TYPE
            )
        )
        if coordinator.device.extra_energy_features:
            for description in ARISTON_HEATING_CONSUMPTION_LAST_MONTH_SENSORS_TYPES:
                ariston_sensors.append(
                    AristonGasEnergyLastMonthSensor(energy_coordinator, description)
                )

        if coordinator.device.features[DeviceFeatures.HAS_BOILER]:
            ariston_sensors.append(
                AristonGasConsumptionLastTwoHours(
                    energy_coordinator,
                    ARISTON_GAS_CONSUMPTION_WATER_LAST_TWO_HOURS_TYPE,
                )
            )
            if coordinator.device.extra_energy_features:
                for description in ARISTON_WATER_CONSUMPTION_LAST_MONTH_SENSORS_TYPES:
                    ariston_sensors.append(
                        AristonGasEnergyLastMonthSensor(energy_coordinator, description)
                    )

    async_add_entities(ariston_sensors)


class AristonSensor(CoordinatorEntity, SensorEntity):
    """Base class for specific ariston sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.entity_description = description
        self.coordinator = coordinator

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


class AristonGasConsumptionLastTwoHours(CoordinatorEntity, SensorEntity):
    """Class for specific ariston energy sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.entity_description = description
        self.coordinator = coordinator
        self.reset_datetime = None
        self.current_consumptions_sequences = None

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


class AristonGasEnergyLastMonthSensor(CoordinatorEntity, SensorEntity):
    """Class for specific ariston energy sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.entity_description = description
        self.coordinator = coordinator

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
