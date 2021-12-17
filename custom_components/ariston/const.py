"""Constants for the Ariston integration."""
from homeassistant.components.binary_sensor import (
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription


DOMAIN = "ariston"
NAME = "Ariston"

ARISTON_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="HeatingCircuitPressure",
        name=f"{NAME} heating circuit pressure",
        device_class=SensorDeviceClass.PRESSURE,
    ),
    SensorEntityDescription(
        key="ChFlowSetpointTemp",
        name=f"{NAME} CH flow setpoint temp",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
)

ARISTON_BINARY_SENSOR_TYPES: tuple[BinarySensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="IsFlameOn",
        name=f"{NAME} is flame on",
        icon="mdi:fire",
    ),
)
