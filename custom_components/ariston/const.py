"""Constants for the Ariston integration."""
from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription

from .ariston import DeviceProperties


DOMAIN = "ariston"
NAME = "Ariston"

ARISTON_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        device_class=SensorDeviceClass.PRESSURE,
    ),
    SensorEntityDescription(
        key=DeviceProperties.CH_FLOW_SETPOINT_TEMP,
        name=f"{NAME} CH flow setpoint temp",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
)

ARISTON_BINARY_SENSOR_TYPES: tuple[BinarySensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=DeviceProperties.IS_FLAME_ON,
        name=f"{NAME} is flame on",
        icon="mdi:fire",
    ),
)
