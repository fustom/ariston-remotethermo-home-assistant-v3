"""Ariston API"""
from __future__ import annotations

import aiohttp
import logging

from typing import Any, final
from datetime import datetime
from enum import IntFlag, unique

ARISTON_API_URL: final = "https://www.ariston-net.remotethermo.com/api/v2/"
ARISTON_LOGIN: final = "accounts/login"
ARISTON_REMOTE: final = "remote"
ARISTON_PLANTS: final = "plants"
ARISTON_LITE: final = "lite"
ARISTON_DATA_ITEMS: final = "dataItems"
ARISTON_ZONES: final = "zones"
ARISTON_PLANT_DATA: final = "plantData"
ARISTON_REPORTS: final = "reports"
ARISTON_TIME_PROGS: final = "timeProgs"

_LOGGER = logging.getLogger(__name__)


@unique
class PlantMode(IntFlag):
    """Plant mode enum"""

    UNDEFINED = -1
    SUMMER = 0
    WINTER = 1
    HEATING_ONLY = 2
    COOLING = 3
    COOLING_ONLY = 4
    OFF = 5


@unique
class ZoneMode(IntFlag):
    """Zone mode enum"""

    UNDEFINED = -1
    OFF = 0
    MANUAL = 1
    MANUAL2 = 2
    TIME_PROGRAM = 3


@unique
class DhwMode(IntFlag):
    """Dhw mode enum"""

    DISABLED = 0
    TIME_BASED = 1
    ALWAYS_ACTIVE = 2
    HC_HP = 3
    HC_HP_40 = 4
    GREEN = 5


@unique
class Weather(IntFlag):
    """Weather enum"""

    UNAVAILABLE = 0
    CLEAR = 1
    VARIABLE = 2
    CLOUDY = 3
    RAINY = 4
    RAINSTORM = 5
    SNOW = 6
    FOG = 7
    WINDY = 8
    CLEAR_BY_NIGHT = 129
    VARIABLE_BY_NIGHT = 130


class DeviceAttribute:
    """Constants for device attributes"""

    GW_FW_VER: final = "gwFwVer"
    GW_ID: final = "gwId"
    GW_LINK: final = "gwLink"
    GW_SERIAL: final = "gwSerial"
    GW_SYS_TYPE: final = "gwSysType"
    PLANT_NAME: final = "plantName"


class ZoneAttribute:
    """Constants for zone attributes"""

    NUM: final = "num"
    NAME: final = "name"
    ROOM_SENS: final = "roomSens"
    GEOFENCE_DEROGA: final = "geofenceDeroga"


class DeviceFeatures:
    """Constants for device features"""

    AUTO_THERMO_REG: final = "autoThermoReg"
    BMS_ACTIVE: final = "bmsActive"
    BUFFER_TIME_PROG_AVAILABLE: final = "bufferTimeProgAvailable"
    CASCDE_SYS: final = "cascadeSys"
    CONV_BOILER: final = "convBoiler"
    DHW_BOILER_PRESENT: final = "dhwBoilerPresent"
    DHW_HIDDEN: final = "dhwHidden"
    DHW_MODE_CHANGEABLE: final = "dhwModeChangeable"
    DHW_PROG_SUPPORTED: final = "dhwProgSupported"
    DICTINCT_HEAT_COOL_SETPOINT: final = "distinctHeatCoolSetpoints"
    EXTENDED_TIME_PROG: final = "extendedTimeProg"
    HAS_BOILER: final = "hasBoiler"
    HAS_EM20: final = "hasEm20"
    HAS_FIREPLACE: final = "hasFireplace"
    HAS_METERING: final = "hasMetering"
    HAS_SLP: final = "hasSlp"
    HAS_TWO_COOLING_TEMP: final = "hasTwoCoolingTemp"
    HAS_VMC: final = "hasVmc"
    HAS_ZONE_NAMES: final = "hasZoneNames"
    HP_CASCADE_CONFIG: final = "hpCascadeConfig"
    HP_CASCADE_SYS: final = "hpCascadeSys"
    HP_SYS: final = "hpSys"
    HV_INPUT_OFF: final = "hvInputOff"
    HYBRID_SYS: final = "hybridSys"
    IS_EVO2: final = "isEvo2"
    IS_VMC_R2: final = "isVmcR2"
    PILOT_SUPPORTED: final = "pilotSupported"
    PRE_HEATING_SUPPORTED: final = "preHeatingSupported"
    SOLAR: final = "solar"
    VIRTUAL_ZONES: final = "virtualZones"
    ZONES: final = "zones"
    WEATHER_PROVIDER: final = "weatherProvider"


class DeviceProperties:
    """Constants for device properties"""

    PLANT_MODE: final = "PlantMode"
    IS_FLAME_ON: final = "IsFlameOn"
    HOLIDAY: final = "Holiday"
    OUTSIDE_TEMP: final = "OutsideTemp"
    HEATING_CIRCUIT_PRESSURE: final = "HeatingCircuitPressure"
    CH_FLOW_SETPOINT_TEMP: final = "ChFlowSetpointTemp"
    DHW_TEMP: final = "DhwTemp"
    DHW_MODE: final = "DhwMode"
    AUTOMATIC_THERMOREGULATION: final = "AutomaticThermoregulation"
    ANTILEGIONELLA_ON_OFF: final = "AntilegionellaOnOff"
    ANTILEGIONELLA_TEMP: final = "AntilegionellaTemp"
    ANTILEGIONELLA_FREQ: final = "AntilegionellaFreq"


class ThermostatProperties:
    """Constants for thermostat properties"""

    ZONE_MEASURED_TEMP: final = "ZoneMeasuredTemp"
    ZONE_DESIRED_TEMP: final = "ZoneDesiredTemp"
    ZONE_COMFORT_TEMP: final = "ZoneComfortTemp"
    ZONE_MODE: final = "ZoneMode"
    ZONE_HEAT_REQUEST: final = "ZoneHeatRequest"
    ZONE_ECONOMY_TEMP: final = "ZoneEconomyTemp"
    ZONE_DEROGA: final = "ZoneDeroga"


class PropertyType:
    """Constants for property types"""

    VALUE: final = "value"
    OPTIONS: final = "options"
    OPT_TEXTS: final = "optTexts"
    UNIT: final = "unit"
    MIN: final = "min"
    MAX: final = "max"
    STEP: final = "step"
    DECIMALS: final = "decimals"


class AristonAPI:
    """Ariston API class"""

    def __init__(self) -> None:
        """Constructor for Ariston API."""
        self.umsys = "si"
        self.token = ""
        self.__username = ""
        self.__password = ""
        self.features = None

    def set_unit_measurement_system(self, is_metric: bool) -> None:
        """Set unit measurement system"""
        self.umsys = "si" if is_metric else "us"

    async def async_connect(self, username: str, password: str) -> bool:
        """Login to ariston cloud and get token"""
        self.__username = username
        self.__password = password

        response = await self.post(
            f"{ARISTON_API_URL}{ARISTON_LOGIN}", {"usr": username, "pwd": password}
        )

        if response is None:
            return False

        self.token = response["token"]

        return True

    async def async_get_detailed_devices(self) -> dict[str, Any]:
        """Get detailed cloud devices"""
        return await self.get(f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_PLANTS}")

    async def async_get_devices(self) -> dict[str, Any]:
        """Get cloud devices"""
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_PLANTS}/{ARISTON_LITE}"
        )

    async def async_get_features_for_device(self, gw_id: str) -> dict[str, Any]:
        """Get features for the device"""
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_PLANTS}/{gw_id}/features"
        )

    async def async_get_energy_account(self, gw_id: str) -> dict[str, Any]:
        """Get energy account for the device"""
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_REPORTS}/{gw_id}/energyAccount"
        )

    async def async_get_consumptions_sequences(
        self, gw_id: str, has_slp: bool
    ) -> dict[str, Any]:
        """Get consumption sequences for the device"""
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_REPORTS}/{gw_id}/consSequencesApi8?usages=Ch%2CDhw&hasSlp={has_slp}"
        )

    async def async_get_consumptions_settings(self, gw_id: str) -> dict[str, Any]:
        """Get consumption settings"""
        return await self.post(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_PLANTS}/{gw_id}/getConsumptionsSettings",
            {},
        )

    async def async_get_device_properties(
        self, gw_id: str, features: dict[str, Any], culture: str
    ) -> dict[str, Any]:
        """Get device properties"""
        return await self.post(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_DATA_ITEMS}/{gw_id}/get?umsys={self.umsys}",
            {
                "items": [
                    {"id": DeviceProperties.PLANT_MODE, "zn": 0},
                    {"id": DeviceProperties.IS_FLAME_ON, "zn": 0},
                    {"id": DeviceProperties.HOLIDAY, "zn": 0},
                    {"id": DeviceProperties.OUTSIDE_TEMP, "zn": 0},
                    {"id": DeviceProperties.HEATING_CIRCUIT_PRESSURE, "zn": 0},
                    {"id": DeviceProperties.CH_FLOW_SETPOINT_TEMP, "zn": 0},
                    {"id": DeviceProperties.DHW_TEMP, "zn": 0},
                    {"id": DeviceProperties.DHW_MODE, "zn": 0},
                    {"id": DeviceProperties.AUTOMATIC_THERMOREGULATION, "zn": 0},
                ],
                "features": features,
                "culture": culture,
            },
        )

    async def async_get_thermostat_properties(
        self, gw_id: str, zone: int, features: dict[str, Any], culture: str
    ) -> dict[str, Any]:
        """Get thermostat properties"""
        return await self.post(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_DATA_ITEMS}/{gw_id}/get?umsys={self.umsys}",
            {
                "items": [
                    {"id": ThermostatProperties.ZONE_MEASURED_TEMP, "zn": zone},
                    {"id": ThermostatProperties.ZONE_DESIRED_TEMP, "zn": zone},
                    {"id": ThermostatProperties.ZONE_COMFORT_TEMP, "zn": zone},
                    {"id": ThermostatProperties.ZONE_MODE, "zn": zone},
                    {"id": ThermostatProperties.ZONE_HEAT_REQUEST, "zn": zone},
                    {"id": ThermostatProperties.ZONE_ECONOMY_TEMP, "zn": zone},
                    {"id": ThermostatProperties.ZONE_DEROGA, "zn": zone},
                ],
                "features": features,
                "culture": culture,
            },
        )

    async def async_set_properties(
        self,
        gw_id: str,
        zone_id: int,
        features: dict[str, Any],
        device_property: str,
        value: float,
        prev_value: float,
    ) -> dict[str, Any]:
        """Set device properties"""
        return await self.post(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_DATA_ITEMS}/{gw_id}/set?umsys={self.umsys}",
            {
                "items": [
                    {
                        "id": device_property,
                        "prevValue": prev_value,
                        "value": value,
                        "zone": zone_id,
                    }
                ],
                "features": features,
            },
        )

    async def async_get_thermostat_time_progs(
        self, gw_id: str, zone: int
    ) -> dict[str, Any]:
        """Get thermostat time programs"""
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_TIME_PROGS}/{gw_id}/ChZn{zone}?umsys={self.umsys}",
        )

    async def async_set_plant_mode(
        self, gw_id: str, mode: PlantMode, current_mode: PlantMode
    ) -> None:
        """Set plant mode"""
        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_PLANT_DATA}/{gw_id}/mode?umsys={self.umsys}",
            {
                "new": mode,
                "old": current_mode,
            },
        )

    async def async_set_zone_mode(
        self, gw_id: str, zone: int, mode: ZoneMode, current_mode: ZoneMode
    ) -> None:
        """Set zone mode"""
        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_ZONES}/{gw_id}/{zone}/mode?umsys={self.umsys}",
            {
                "new": mode,
                "old": current_mode,
            },
        )

    async def async_set_holiday(
        self,
        gw_id: str,
        holiday_end_datetime: datetime,
        current_holiday_end_datetime: datetime,
    ) -> None:
        """Set holidays"""
        holiday_end = (
            None
            if holiday_end_datetime is None
            else holiday_end_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        )
        current_holiday_end = (
            None
            if current_holiday_end_datetime is None
            else current_holiday_end_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        )

        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_PLANT_DATA}/{gw_id}/holiday",
            {
                "new": holiday_end,
                "old": current_holiday_end,
            },
        )

    async def __request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] = None,
        body: dict[str, Any] = None,
        is_retry: bool = False,
    ) -> dict[str, Any]:
        headers = {"ar.authToken": self.token}

        async with aiohttp.ClientSession() as session:
            response = await session.request(
                method, path, params=params, json=body, headers=headers
            )

            if not response.ok:
                if response.status == 405:
                    if not is_retry:
                        if await self.async_connect(self.__username, self.__password):
                            return await self.__request(
                                method, path, params, body, True
                            )
                        raise Exception("Login failed (password changed?)")
                    raise Exception("Invalid token")
                if response.status == 404:
                    return None
                raise Exception(response.status)

            if response.content_length > 0:
                json = await response.json()
                _LOGGER.debug(json)
                return json

            return None

    async def post(self, path: str, body: dict[str, Any] = None) -> dict[str, Any]:
        """POST request"""
        return await self.__request("POST", path, None, body)

    async def get(self, path: str, params: dict[str, Any] = None) -> dict[str, Any]:
        """GET request"""
        return await self.__request("GET", path, params, None)
