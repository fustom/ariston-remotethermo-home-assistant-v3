"""Ariston API"""
from __future__ import annotations

import aiohttp
import logging

from typing import Any
from datetime import datetime
from enum import IntFlag, unique

ARISTON_API_URL = "https://www.ariston-net.remotethermo.com/api/v2/"
ARISTON_LOGIN = "accounts/login"
ARISTON_REMOTE = "remote"
ARISTON_PLANTS = "plants"
ARISTON_LITE = "lite"
ARISTON_DATA_ITEMS = "dataItems"
ARISTON_ZONES = "zones"
ARISTON_PLANT_DATA = "plantData"
ARISTON_REPORTS = "reports"

WATER_HEATER_REQUEST_ITEMS = [
    {"id": "DhwMode", "zn": 0},
    {"id": "DhwTemp", "zn": 0},
]

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


class AristonAPI:
    """Ariston API class"""

    def __init__(self) -> None:
        """Constructor for Ariston API."""
        self.token = ""
        self.__username = ""
        self.__password = ""

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

    async def async_get_device_properies(
        self, gw_id: str, zone: int, features: dict[str, Any], culture: str
    ) -> dict[str, Any]:
        """Get device items by request body"""
        return await self.post(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_DATA_ITEMS}/{gw_id}/get",
            {
                "items": [
                    {"id": "ZoneMeasuredTemp", "zn": zone},
                    {"id": "ZoneDesiredTemp", "zn": zone},
                    {"id": "ZoneComfortTemp", "zn": zone},
                    {"id": "ZoneMode", "zn": zone},
                    {"id": "ZoneHeatRequest", "zn": zone},
                    {"id": "ZoneEconomyTemp", "zn": zone},
                    {"id": "PlantMode", "zn": 0},
                    {"id": "IsFlameOn", "zn": 0},
                    {"id": "Holiday", "zn": 0},
                    {"id": "OutsideTemp", "zn": 0},
                    {"id": "HeatingCircuitPressure", "zn": 0},
                    {"id": "ChFlowSetpointTemp", "zn": 0},
                ],
                "features": features,
                "culture": culture,
            },
        )

    async def async_get_water_heater_properties(
        self, gw_id: str, features: dict[str, Any], culture: str
    ) -> dict[str, Any]:
        """Get water heater properties"""
        return await self.post(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_DATA_ITEMS}/{gw_id}/get",
            {
                "items": WATER_HEATER_REQUEST_ITEMS,
                "features": features,
                "culture": culture,
            },
        )

    async def async_set_temperature(
        self, gw_id: str, zone: int, temperature: float, current_temperature: float
    ) -> None:
        """Set comfort temperature"""
        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_ZONES}/{gw_id}/{zone}/temperatures",
            {
                "new": {"comf": temperature},
                "old": {"comf": current_temperature},
            },
        )

    async def async_set_plant_mode(
        self, gw_id: str, mode: PlantMode, current_mode: PlantMode
    ) -> None:
        """Set plant mode"""
        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_PLANT_DATA}/{gw_id}/mode",
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
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_ZONES}/{gw_id}/{zone}/mode",
            {
                "new": mode,
                "old": current_mode,
            },
        )

    async def async_set_dhwtemp(
        self, gw_id: str, temperature: float, current_temperature: float
    ) -> None:
        """Set domestic hot water temperature"""
        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_PLANT_DATA}/{gw_id}/dhwTemp",
            {
                "new": temperature,
                "old": current_temperature,
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
