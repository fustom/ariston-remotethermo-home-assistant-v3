"""Constants for the Ariston integration."""
from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription

from .ariston import DeviceProperties


DOMAIN = "ariston"
NAME = "Ariston"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)

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
    SensorEntityDescription(
        key=DeviceProperties.HOLIDAY,
        name=f"{NAME} holiday mode",
        icon="mdi:island",
    ),
)

ARISTON_SWITCH_TYPES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key=DeviceProperties.AUTOMATIC_THERMOREGULATION,
        name=f"{NAME} automatic thermoregulation",
        icon="mdi:radiator",
    ),
)
