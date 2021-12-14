import aiohttp
import logging
from typing import Any
from datetime import datetime
from enum import IntFlag

ARISTON_API_URL = "https://www.ariston-net.remotethermo.com/api/v2/"
ARISTON_LOGIN = "accounts/login"
ARISTON_REMOTE = "remote"
ARISTON_PLANTS = "plants"
ARISTON_LITE = "lite"
ARISTON_DATA_ITEMS = "dataItems"
ARISTON_ZONES = "zones"
ARISTON_PLANT_DATA = "plantData"
ARISTON_REPORTS = "reports"

_LOGGER = logging.getLogger(__name__)


class PlantMode(IntFlag):
    SUMMER = 0
    WINTER = 1
    HEATING_ONLY = 2
    COOLING = 3
    OFF = 5


class ZoneMode(IntFlag):
    OFF = 0
    MANUAL = 2
    TIME_PROGRAM = 3


class AristonAPI:
    def __init__(self) -> None:
        """Init AristonAPI."""
        self.token = ""
        self.__username = ""
        self.__password = ""

    async def connect(self, username: str, password: str) -> bool:
        self.__username = username
        self.__password = password

        response = await self.post(
            f"{ARISTON_API_URL}{ARISTON_LOGIN}", {"usr": username, "pwd": password}
        )

        if response is None:
            return False

        self.token = response["token"]

        return True

    async def get_devices(self) -> dict[str, Any]:
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_PLANTS}/{ARISTON_LITE}"
        )

    async def get_features_for_device(self, gw_id: str) -> dict[str, Any]:
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_PLANTS}/{gw_id}/features"
        )

    async def get_energy_account(self, gw_id: str) -> dict[str, Any]:
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_REPORTS}/{gw_id}/energyAccount"
        )

    async def get_consumptions_sequences(
        self, gw_id: str, hasSlp: bool
    ) -> dict[str, Any]:
        return await self.get(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_REPORTS}/{gw_id}/consSequencesApi8?usages=Ch%2CDhw&hasSlp={hasSlp}"
        )

    async def get_consumptions_settings(self, gw_id: str) -> dict[str, Any]:
        return await self.post(
            f"{ARISTON_API_URL}{ARISTON_REMOTE}/{ARISTON_PLANTS}/{gw_id}/getConsumptionsSettings",
            {},
        )

    async def update_device(
        self, gw_id: str, zone: int, features: dict[str, Any], culture: str
    ) -> dict[str, Any]:
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
                    {"id": "DhwTemp", "zn": 0},
                    {"id": "HeatingCircuitPressure", "zn": 0},
                    {"id": "ChFlowSetpointTemp", "zn": 0},
                    {"id": "DhwMode", "zn": 0},
                    {"id": "DhwTemp", "zn": 0},
                ],
                "features": features,
                "culture": culture,
            },
        )

    async def set_temperature(
        self, gw_id: str, zone: int, temperature: float, current_temperature: float
    ) -> None:
        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_ZONES}/{gw_id}/{zone}/temperatures",
            {
                "new": {"comf": temperature},
                "old": {"comf": current_temperature},
            },
        )

    async def set_plant_mode(
        self, gw_id: str, mode: PlantMode, current_mode: PlantMode
    ) -> None:
        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_PLANT_DATA}/{gw_id}/mode",
            {
                "new": mode,
                "old": current_mode,
            },
        )

    async def set_zone_mode(
        self, gw_id: str, zone: int, mode: ZoneMode, current_mode: ZoneMode
    ) -> None:
        await self.post(
            f"{ARISTON_API_URL}/{ARISTON_REMOTE}/{ARISTON_ZONES}/{gw_id}/{zone}/mode",
            {
                "new": mode,
                "old": current_mode,
            },
        )

    async def set_holiday(
        self,
        gw_id: str,
        holiday_end_datetime: datetime,
        current_holiday_end_datetime: datetime,
    ) -> None:
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
                        if await self.connect(self.__username, self.__password):
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
        return await self.__request("POST", path, None, body)

    async def get(self, path: str, params: dict[str, Any] = None) -> dict[str, Any]:
        return await self.__request("GET", path, params, None)
