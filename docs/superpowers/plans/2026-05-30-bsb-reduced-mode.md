# BSB Reduced Mode & Temperature Entities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the "Réduit" (MANUAL_NIGHT) zone mode as a preset in the BSB climate entity, and add Number entities for the per-zone and DHW reduced temperature setpoints.

**Architecture:** Two changes in parallel: (1) `climate.py` gets preset mode support for BSB by checking `device.system_type == SystemType.BSB` and routing to `BsbZoneMode.MANUAL_NIGHT`; (2) `const.py` gets two new `AristonNumberEntityDescription` entries for zone and DHW reduced temps, which `number.py` picks up automatically via its existing zone-aware loop.

**Tech Stack:** Home Assistant custom component, Python 3.13, `ariston==0.19.9` library (BSB device class)

---

## File Map

| File | Change |
|------|--------|
| `custom_components/ariston/const.py` | Add `BSB_PRESET_COMFORT`, `BSB_PRESET_REDUCED` string constants; add 2 `AristonNumberEntityDescription` entries to `ARISTON_NUMBER_TYPES` |
| `custom_components/ariston/climate.py` | Import `SystemType`, `BSB_PRESET_COMFORT`, `BSB_PRESET_REDUCED`; update `supported_features`, `preset_modes`, `preset_mode`, `target_temperature`, `async_set_preset_mode`, `async_set_temperature` |

`number.py` requires no changes — its existing loop already handles `zone=True` descriptions.

---

## Task 1: Add BSB preset constants to const.py

**Files:**
- Modify: `custom_components/ariston/const.py`

- [ ] **Step 1: Add the two preset name constants**

Open `custom_components/ariston/const.py`. After the `ELCO_API_URL` line (around line 62), add:

```python
BSB_PRESET_COMFORT: Final[str] = "Confort"
BSB_PRESET_REDUCED: Final[str] = "Réduit"
```

- [ ] **Step 2: Verify the file parses cleanly**

```bash
python3 -c "from custom_components.ariston.const import BSB_PRESET_COMFORT, BSB_PRESET_REDUCED; print(BSB_PRESET_COMFORT, BSB_PRESET_REDUCED)"
```

Expected output: `Confort Réduit`

- [ ] **Step 3: Commit**

```bash
git add custom_components/ariston/const.py
git commit -m "Add BSB_PRESET_COMFORT and BSB_PRESET_REDUCED constants"
```

---

## Task 2: Add BSB reduced temperature Number entities to const.py

**Files:**
- Modify: `custom_components/ariston/const.py`

- [ ] **Step 1: Add the zone reduced temperature entity description**

In `custom_components/ariston/const.py`, inside `ARISTON_NUMBER_TYPES` (after the last existing entry, before the closing `]`), add:

```python
    AristonNumberEntityDescription(
        key="BsbZoneReducedTemp",
        name=f"{NAME} reduced temp",
        icon="mdi:thermometer-chevron-down",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        zone=True,
        get_native_min_value=lambda entity: entity.device.get_reduced_temp_min(
            entity.zone
        ),
        get_native_max_value=lambda entity: entity.device.get_reduced_temp_max(
            entity.zone
        ),
        get_native_step=lambda entity: entity.device.get_reduced_temp_step(
            entity.zone
        ),
        get_native_value=lambda entity: entity.device.get_reduced_temp_value(
            entity.zone
        ),
        set_native_value=lambda entity, value: entity.device.async_set_reduced_temp(
            value, entity.zone
        ),
        system_types=[SystemType.BSB],
    ),
    AristonNumberEntityDescription(
        key="BsbDhwReducedTemp",
        name=f"{NAME} DHW reduced temp",
        icon="mdi:thermometer-chevron-down",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_features=[CustomDeviceFeatures.HAS_DHW],
        get_native_min_value=lambda entity: entity.device.water_heater_reduced_minimum_temperature,
        get_native_max_value=lambda entity: entity.device.water_heater_reduced_maximum_temperature,
        get_native_step=lambda entity: entity.device.water_heater_reduced_temperature_step,
        get_native_value=lambda entity: entity.device.water_heater_reduced_temperature,
        set_native_value=lambda entity,
        value: entity.device.async_set_water_heater_reduced_temperature(value),
        system_types=[SystemType.BSB],
    ),
```

- [ ] **Step 2: Verify the file parses cleanly**

```bash
python3 -c "from custom_components.ariston.const import ARISTON_NUMBER_TYPES; bsb = [e for e in ARISTON_NUMBER_TYPES if e.key in ('BsbZoneReducedTemp','BsbDhwReducedTemp')]; print([e.key for e in bsb])"
```

Expected: `['BsbZoneReducedTemp', 'BsbDhwReducedTemp']`

- [ ] **Step 3: Commit**

```bash
git add custom_components/ariston/const.py
git commit -m "Add BSB reduced temperature Number entity descriptions"
```

---

## Task 3: Add BSB preset mode support to climate.py

**Files:**
- Modify: `custom_components/ariston/climate.py`

- [ ] **Step 1: Update imports**

In `custom_components/ariston/climate.py`, change the `ariston.const` import line from:

```python
from ariston.const import PlantMode, ZoneMode, BsbZoneMode
```

to:

```python
from ariston.const import BsbZoneMode, PlantMode, SystemType, ZoneMode
```

And change the `.const` import to add the two new constants:

```python
from .const import (
    ARISTON_CLIMATE_TYPES,
    BSB_PRESET_COMFORT,
    BSB_PRESET_REDUCED,
    DOMAIN,
    AristonClimateEntityDescription,
)
```

- [ ] **Step 2: Update `supported_features`**

Replace the existing `supported_features` property:

```python
@property
def supported_features(self) -> int:
    """Return the supported features for this device integration."""
    features = ClimateEntityFeature.TARGET_TEMPERATURE
    if hasattr(ClimateEntityFeature, "TURN_OFF"):
        features |= ClimateEntityFeature.TURN_OFF
    if hasattr(ClimateEntityFeature, "TURN_ON"):
        features |= ClimateEntityFeature.TURN_ON
    if self.device.plant_mode_supported or self.device.system_type == SystemType.BSB:
        features |= ClimateEntityFeature.PRESET_MODE
    return features
```

- [ ] **Step 3: Update `preset_modes`**

Replace the existing `preset_modes` property:

```python
@property
def preset_modes(self) -> list[str]:
    """Return a list of available preset modes."""
    if self.device.system_type == SystemType.BSB:
        return [BSB_PRESET_COMFORT, BSB_PRESET_REDUCED]
    return self.device.plant_mode_opt_texts
```

- [ ] **Step 4: Update `preset_mode`**

Replace the existing `preset_mode` property:

```python
@property
def preset_mode(self) -> str | None:
    """Return the current preset mode."""
    if self.device.system_type == SystemType.BSB:
        zone_mode = self.device.get_zone_mode(self.zone)
        if zone_mode == BsbZoneMode.MANUAL:
            return BSB_PRESET_COMFORT
        if zone_mode == BsbZoneMode.MANUAL_NIGHT:
            return BSB_PRESET_REDUCED
        return None
    return self.device.plant_mode_text
```

- [ ] **Step 5: Update `target_temperature`**

Replace the existing `target_temperature` property:

```python
@property
def target_temperature(self) -> float:
    """Return the target temperature for the device."""
    if (
        self.device.system_type == SystemType.BSB
        and self.device.get_zone_mode(self.zone) == BsbZoneMode.MANUAL_NIGHT
    ):
        return self.device.get_reduced_temp_value(self.zone)
    return self.device.get_target_temp_value(self.zone)
```

- [ ] **Step 6: Update `async_set_temperature`**

Replace the existing `async_set_temperature` method:

```python
async def async_set_temperature(self, **kwargs):
    """Set new target temperature."""
    if ATTR_TEMPERATURE not in kwargs:
        raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")

    temperature = kwargs[ATTR_TEMPERATURE]
    _LOGGER.debug(
        "Setting temperature to %s for %s",
        temperature,
        self.name,
    )

    if (
        self.device.system_type == SystemType.BSB
        and self.device.get_zone_mode(self.zone) == BsbZoneMode.MANUAL_NIGHT
    ):
        await self.device.async_set_reduced_temp(temperature, self.zone)
    else:
        await self.device.async_set_comfort_temp(temperature, self.zone)
    self.async_write_ha_state()
```

- [ ] **Step 7: Add `async_set_preset_mode` for BSB**

The existing `async_set_preset_mode` handles GALEVO. Prepend a BSB branch at the top of the method body:

```python
async def async_set_preset_mode(self, preset_mode: str) -> None:
    """Set new target preset mode."""
    _LOGGER.debug(
        "Setting preset mode to %s for %s",
        preset_mode,
        self.name,
    )

    if self.device.system_type == SystemType.BSB:
        if preset_mode == BSB_PRESET_COMFORT:
            await self.device.async_set_zone_mode(BsbZoneMode.MANUAL, self.zone)
        elif preset_mode == BSB_PRESET_REDUCED:
            await self.device.async_set_zone_mode(BsbZoneMode.MANUAL_NIGHT, self.zone)
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()
        return

    # GALEVO path — existing logic below unchanged
    preset_index = self.device.plant_mode_opt_texts.index(preset_mode)
    plant_mode = PlantMode(self.device.plant_mode_options[preset_index])

    current_plant_in_cool = self.device.is_plant_in_cool_mode
    zone_modes = self.device.get_zone_mode_options(self.zone)

    if current_plant_in_cool and plant_mode != PlantMode.COOLING:
        if ZoneMode.MANUAL in zone_modes:
            await self.device.async_set_zone_mode(ZoneMode.MANUAL, self.zone)

    await self.device.async_set_plant_mode(plant_mode)

    if plant_mode == PlantMode.OFF:
        if self.device.is_zone_mode_options_contains_off(self.zone):
            await self.device.async_set_zone_mode(BsbZoneMode.OFF, self.zone)

    await self.coordinator.async_request_refresh()
    self.async_write_ha_state()
```

- [ ] **Step 8: Verify the file parses cleanly**

```bash
python3 -c "
import ast, sys
with open('custom_components/ariston/climate.py') as f:
    src = f.read()
ast.parse(src)
print('OK')
"
```

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add custom_components/ariston/climate.py
git commit -m "Add Confort/Réduit preset modes and reduced temperature support for BSB devices"
```

---

## Task 4: Push and open PR

- [ ] **Step 1: Check overall diff**

```bash
git log main..HEAD --oneline
```

Expected: 3 commits (constants, number entities, climate changes).

- [ ] **Step 2: Push branch and open PR**

```bash
git push fork feature/bsb-reduced-mode
gh pr create \
  --repo c3dcmps/ariston-remotethermo-home-assistant-v3 \
  --head feature/bsb-reduced-mode \
  --base main \
  --title "Add Réduit (MANUAL_NIGHT) preset mode and reduced temperature entities for BSB devices" \
  --body "$(cat <<'EOF'
## What this does

For BSB devices (e.g. Elco Aerotop), the Remocon portal exposes four zone modes:
Auto, Confort, Réduit, and Éteint. Previously only three were reachable in HA
(Auto/Chauffage/Éteint) — BsbZoneMode.MANUAL_NIGHT was silently dropped.

### Changes

**Climate entity:**
- Adds \`Confort\` and \`Réduit\` as preset modes when \`HVACMode.HEAT\` is active
- Selecting \`Réduit\` sets \`BsbZoneMode.MANUAL_NIGHT\`; \`Confort\` sets \`BsbZoneMode.MANUAL\`
- \`target_temperature\` shows the reduced setpoint when in MANUAL_NIGHT
- \`async_set_temperature\` routes to \`async_set_reduced_temp\` when in MANUAL_NIGHT

**Number entities (BSB only):**
- \`reduced temp\` — per-zone reduced temperature setpoint (settable)
- \`DHW reduced temp\` — hot water night setpoint (settable, requires DHW)

GALEVO behaviour is unchanged.

## Tested with
Elco Aerotop S09.2 via Remocon NET (BSB system type)
EOF
)"
```
