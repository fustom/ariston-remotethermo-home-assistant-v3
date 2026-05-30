# BSB Reduced Mode & Temperature Entities

**Date:** 2026-05-30
**Device:** Elco Aerotop S09.2 (system type: BSB) via Remocon NET

## Problem

The Remocon portal exposes four zone modes: Auto, Confort, Réduit, Éteint. The HA
integration only surfaces three: Auto, Chauffage (HEAT), Éteint. `BsbZoneMode.MANUAL_NIGHT`
("Réduit") is silently collapsed into HEAT and is unreachable from HA.

Additionally, two temperature setpoints visible in the portal are not exposed as HA entities:
- Per-zone reduced temperature (used in Réduit mode)
- DHW reduced temperature (hot water night setpoint)

## Design

### 1. Climate entity — BSB preset modes

Add `ClimateEntityFeature.PRESET_MODE` to the BSB climate entity's `supported_features`.

**New constants (in `const.py`):**
```python
BSB_PRESET_COMFORT = "Confort"
BSB_PRESET_REDUCED = "Réduit"
```

**`preset_modes` property:**
Returns `[BSB_PRESET_COMFORT, BSB_PRESET_REDUCED]` for BSB devices.
Returns `[]` (empty / no change) for GALEVO devices.

**`preset_mode` property:**
- `BsbZoneMode.MANUAL` → `BSB_PRESET_COMFORT`
- `BsbZoneMode.MANUAL_NIGHT` → `BSB_PRESET_REDUCED`
- Any other mode → `None`

**`target_temperature` property (BSB adaptation):**
- Zone mode is `MANUAL_NIGHT` → `device.get_reduced_temp_value(zone)`
- Otherwise → existing `device.get_target_temp_value(zone)` (comfort temp)

**`async_set_preset_mode`:**
- `BSB_PRESET_COMFORT` → `device.async_set_zone_mode(BsbZoneMode.MANUAL, zone)`
- `BSB_PRESET_REDUCED` → `device.async_set_zone_mode(BsbZoneMode.MANUAL_NIGHT, zone)`

**`async_set_temperature` (BSB adaptation):**
- Active zone mode is `MANUAL_NIGHT` → `device.async_set_reduced_temp(temp, zone)`
- Otherwise → existing `device.async_set_comfort_temp(temp, zone)`

GALEVO paths are not touched.

### 2. Number entities — BSB reduced temperatures

Two new entries in `ARISTON_NUMBER_TYPES` in `const.py`, following the existing
`AristonNumberEntityDescription` pattern.

**Zone reduced temperature (per zone):**
```
key:       "BsbZoneReducedTemp"
system:    SystemType.BSB
get_value: device.get_reduced_temp_value(zone)
min:       device.get_reduced_temp_min(zone)
max:       device.get_reduced_temp_max(zone)
step:      device.get_reduced_temp_step(zone)
set_value: device.async_set_reduced_temp(value, zone)
unit:      °C, device_class: temperature
```

**DHW reduced temperature:**
```
key:       "BsbDhwReducedTemp"
system:    SystemType.BSB
feature:   CustomDeviceFeatures.HAS_DHW
get_value: device.water_heater_reduced_temperature
min:       device.water_heater_reduced_minimum_temperature
max:       device.water_heater_reduced_maximum_temperature
step:      device.water_heater_reduced_temperature_step
set_value: device.async_set_water_heater_reduced_temperature(value)
unit:      °C, device_class: temperature
```

## Files to change

| File | Change |
|------|--------|
| `const.py` | Add `BSB_PRESET_COMFORT`, `BSB_PRESET_REDUCED` constants; add 2 Number entity descriptions |
| `climate.py` | Add preset mode support to BSB path in `supported_features`, `preset_modes`, `preset_mode`, `target_temperature`, `async_set_preset_mode`, `async_set_temperature` |
| `number.py` | Ensure zone-aware Number entities work for BSB (check zone iteration logic) |

## Out of scope

- GALEVO device changes
- CH flow/return temperature sensors (not available from BSB API)
- Manufacturer name fix (config entry reconfiguration, not code)
