"""Support for Ariston boilers."""
import logging

from .ariston import AristonAPI, PlantMode, ZoneMode
from .const import DOMAIN, FEATURES, API

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_DEVICE,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    ATTR_TEMPERATURE,
)
from homeassistant.components.climate import ClimateEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.climate.const import (
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    HVAC_MODE_COOL,
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_IDLE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston device from config entry."""
    api: AristonAPI = hass.data[DOMAIN][API]
    device = entry.data[CONF_DEVICE]
    features = hass.data[DOMAIN][FEATURES]
    zones = features["zones"]
    devs = []
    for zone in zones:
        ariston_zone_device = AristonDevice(api, device, features, zone["num"])
        await ariston_zone_device.async_update()
        devs.append(ariston_zone_device)
    async_add_entities(devs)


class AristonDevice(ClimateEntity):
    """Representation of a base Ariston discovery device."""

    def __init__(self, api: AristonAPI, device, features, zone):
        """Initialize the entity."""
        self.api = api
        self.features = features
        self.zone = zone

        self.location = "en-US"

        # device specific variables
        self.gw_id = device["gwId"]
        self.gw_serial = device["gwSerial"]
        self.plant_name = device["plantName"]
        self.gw_fw_ver = device["gwFwVer"]
        self.gw_sys_type = device["gwSysType"]
        self.model = ""
        if self.gw_sys_type == 3:  # I'm not sure at all
            self.model = "Alteas One"

        self.plant_mode = None
        self.is_flame_on = None

        # zone specific variables
        self.zone_comfort_temp = None
        self.zone_measured_temp = None
        self.zone_mode = None

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.plant_name

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return f"{self.gw_id}_{self.zone}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gw_serial)},
            manufacturer="Ariston",
            name=self.plant_name,
            sw_version=self.gw_fw_ver,
            model=self.model,
        )

    @property
    def icon(self):
        """Return the name of the Climate device."""
        plant_mode = PlantMode(self.plant_mode["value"])

        if plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
            return "mdi:radiator"
        else:
            return "mdi:radiator-off"

    @property
    def temperature_unit(self) -> str:
        """Return the temperature units for the device."""
        return (
            TEMP_CELSIUS if self.zone_measured_temp["unit"] == "°C" else TEMP_FAHRENHEIT
        )

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10 ** self.zone_measured_temp["decimals"]

    @property
    def min_temp(self):
        """Return minimum temperature."""
        return self.zone_comfort_temp["min"]

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.zone_comfort_temp["max"]

    @property
    def target_temperature_step(self) -> float:
        """Return the target temperature step support by the device."""
        return self.zone_comfort_temp["step"]

    @property
    def current_temperature(self) -> float:
        """Return the reported current temperature for the device."""
        return self.zone_measured_temp["value"]

    @property
    def target_temperature(self) -> float:
        """Return the target temperature for the device."""
        return self.zone_comfort_temp["value"]

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        return SUPPORT_FLAGS

    @property
    def hvac_mode(self) -> str:
        """Return the current HVAC mode for the device."""
        plant_mode = PlantMode(self.plant_mode["value"])
        zone_mode = ZoneMode(self.zone_mode["value"])

        curr_hvac_mode = HVAC_MODE_OFF
        if plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
            if zone_mode == ZoneMode.MANUAL:
                curr_hvac_mode = HVAC_MODE_HEAT
            elif zone_mode == ZoneMode.TIME_PROGRAM:
                curr_hvac_mode = HVAC_MODE_AUTO
        if plant_mode in [PlantMode.COOLING]:
            if zone_mode == ZoneMode.MANUAL:
                curr_hvac_mode = HVAC_MODE_COOL
            elif zone_mode == ZoneMode.TIME_PROGRAM:
                curr_hvac_mode = HVAC_MODE_AUTO
        return curr_hvac_mode

    @property
    def hvac_modes(self) -> list[str]:
        """Return the HVAC modes support by the device."""
        plant_modes = self.plant_mode["options"]
        zone_modes = self.zone_mode["options"]

        supported_modes = []
        if ZoneMode.MANUAL in zone_modes:
            supported_modes.append(HVAC_MODE_HEAT)
            if PlantMode.COOLING in plant_modes:
                supported_modes.append(HVAC_MODE_COOL)
        if ZoneMode.TIME_PROGRAM in zone_modes:
            supported_modes.append(HVAC_MODE_AUTO)
        if ZoneMode.OFF in zone_modes:
            supported_modes.append(HVAC_MODE_OFF)

        return supported_modes

    @property
    def hvac_action(self):
        """Return the current running hvac operation."""
        plant_mode = PlantMode(self.plant_mode["value"])
        if_flame_on = self.is_flame_on["value"] == 1

        curr_hvac_action = CURRENT_HVAC_OFF
        if plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
            if if_flame_on:
                curr_hvac_action = CURRENT_HVAC_HEAT
            else:
                curr_hvac_action = CURRENT_HVAC_IDLE
        if plant_mode in [PlantMode.COOLING]:
            if if_flame_on:
                curr_hvac_action = CURRENT_HVAC_COOL
            else:
                curr_hvac_action = CURRENT_HVAC_IDLE
        return curr_hvac_action

    @property
    def preset_mode(self) -> str:
        """Return the current preset mode, e.g., home, away, temp."""
        res = self.plant_mode["options"].index(self.plant_mode["value"])
        return self.plant_mode["optTexts"][res]

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        return self.plant_mode["optTexts"]

    def set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        plant_modes = self.plant_mode["options"]
        plant_mode = PlantMode(self.plant_mode["value"])

        if hvac_mode == HVAC_MODE_OFF:
            if PlantMode.OFF in plant_modes:
                self.api.set_plant_mode(
                    self.gw_id, PlantMode.OFF, PlantMode(self.preset_mode)
                )
            else:
                self.api.set_plant_mode(
                    self.gw_id, PlantMode.SUMMER, PlantMode(self.preset_mode)
                )
        elif hvac_mode == HVAC_MODE_AUTO:
            zone_mode = ZoneMode.TIME_PROGRAM
            if plant_mode in [
                PlantMode.WINTER,
                PlantMode.HEATING_ONLY,
                PlantMode.COOLING,
            ]:
                # if already heating or cooling just change CH mode
                self.api.set_zone_mode(
                    self.gw_id,
                    self.zone,
                    zone_mode,
                    self.zone_mode["value"],
                )
            elif plant_mode == PlantMode.SUMMER:
                # DHW is working, so use Winter where CH and DHW are active
                self.api.set_plant_mode(
                    self.gw_id, PlantMode.WINTER, PlantMode(self.preset_mode)
                )
                self.api.set_zone_mode(
                    self.gw_id,
                    self.zone,
                    zone_mode,
                    self.zone_mode["value"],
                )
            else:
                # hvac is OFF, so use heating only, if not supported then winter
                if PlantMode.HEATING_ONLY in plant_modes:
                    self.api.set_plant_mode(
                        self.gw_id,
                        PlantMode.HEATING_ONLY,
                        PlantMode(self.preset_mode),
                    )
                    self.api.set_zone_mode(
                        self.gw_id,
                        self.zone,
                        zone_mode,
                        self.zone_mode["value"],
                    )
                else:
                    self.api.set_plant_mode(
                        self.gw_id, PlantMode.WINTER, PlantMode(self.preset_mode)
                    )
                    self.api.set_zone_mode(
                        self.gw_id,
                        self.zone,
                        zone_mode,
                        self.zone_mode["value"],
                    )
        elif hvac_mode == HVAC_MODE_HEAT:
            zone_mode = ZoneMode.MANUAL
            if plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
                # if already heating, change CH mode
                self.api.set_zone_mode(
                    self.gw_id,
                    self.zone,
                    zone_mode,
                    self.zone_mode["value"],
                )
            elif plant_mode in [PlantMode.SUMMER, PlantMode.COOLING]:
                # DHW is working, so use Winter and change mode
                self.api.set_plant_mode(
                    self.gw_id, PlantMode.WINTER, PlantMode(self.preset_mode)
                )
                self.api.set_zone_mode(
                    self.gw_id,
                    self.zone,
                    zone_mode,
                    self.zone_mode["value"],
                )
            else:
                # hvac is OFF, so use heating only, if not supported then winter
                if PlantMode.HEATING_ONLY in plant_modes:
                    self.api.set_plant_mode(
                        self.gw_id,
                        PlantMode.HEATING_ONLY,
                        PlantMode(self.preset_mode),
                    )
                    self.api.set_zone_mode(
                        self.gw_id,
                        self.zone,
                        zone_mode,
                        self.zone_mode["value"],
                    )
                else:
                    self.api.set_plant_mode(
                        self.gw_id, PlantMode.WINTER, PlantMode(self.preset_mode)
                    )
                    self.api.set_zone_mode(
                        self.gw_id,
                        self.zone,
                        zone_mode,
                        self.zone_mode["value"],
                    )
        elif hvac_mode == HVAC_MODE_COOL:
            zone_mode = ZoneMode.MANUAL
            self.api.set_plant_mode(
                self.gw_id, PlantMode.COOLING, PlantMode(self.preset_mode)
            )
            self.api.set_zone_mode(
                self.gw_id, self.zone, zone_mode, self.zone_mode["value"]
            )

    def set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        _LOGGER.debug(
            "Setting preset mode to %d for %s",
            preset_mode,
            self.name,
        )

        self.api.set_plant_mode(self.gw_id, preset_mode, PlantMode(self.preset_mode))

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")

        temperature = kwargs[ATTR_TEMPERATURE]
        _LOGGER.debug(
            "Setting temperature to %d for %s",
            temperature,
            self.name,
        )

        await self.api.set_temperature(
            self.gw_id, self.zone, temperature, self.target_temperature
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        data = await self.api.update_device(
            self.gw_id, self.zone, self.features, self.location
        )
        for item in data["items"]:
            if item["id"] == "ZoneComfortTemp":
                self.zone_comfort_temp = item
            if item["id"] == "ZoneMeasuredTemp":
                self.zone_measured_temp = item
            if item["id"] == "PlantMode":
                self.plant_mode = item
            if item["id"] == "ZoneMode":
                self.zone_mode = item
            if item["id"] == "IsFlameOn":
                self.is_flame_on = item
