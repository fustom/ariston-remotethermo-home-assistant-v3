# Ariston NET for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![Tests](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/tests.yml/badge.svg)](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/tests.yml)
[![Validate with hassfest](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/hassfest.yml/badge.svg)](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/hassfest.yml)
[![HACS Action](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/hacs.yml/badge.svg)](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/hacs.yml)
[![CodeQL](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/codeql.yml)

Control heating zones and hot water, check device status, and track energy use on supported Ariston NET devices in Home Assistant. This custom integration connects to the Ariston NET cloud. It needs an internet connection and an Ariston NET account with your device already registered.

> **Co-maintainers wanted.** [See how you can help](#co-maintainers-wanted).

[Installation](#installation) · [Devices and features](#devices-and-features) · [Options](#options) · [Energy monitoring](#energy-monitoring) · [Automation actions](#automation-actions) · [Support](#support)

## Installation

The current release requires **Home Assistant 2026.10.4 or later**. See the [release notes](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/releases) for changes in each version.

### With HACS

[![Open Ariston NET in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fustom&repository=ariston-remotethermo-home-assistant-v3&category=integration)

1. In HACS, search for **Ariston NET** or use the button above.
2. Select **Download**.
3. Restart Home Assistant.

### Manual installation

1. Download `ariston-remotethermo-home-assistant-v3.zip` from the [latest release](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/releases/latest).
2. Extract the contents into `custom_components/ariston` in your Home Assistant configuration directory. Check that the manifest is at `custom_components/ariston/manifest.json`.
3. Restart Home Assistant.

### Add your device

1. In Home Assistant, go to **Settings → Devices & services → Add integration**.
2. Search for **Ariston** and enter your Ariston NET username and password. Keep the default API URL and user agent for standard setup.
3. If the account has several devices, select one. Repeat **Add integration** for each additional device.

## Devices and features

The integration adds entities according to the system type, model, and features that the Ariston NET cloud reports. The table gives examples of what you can use.

| Device family | Available features |
| --- | --- |
| **GALEVO** boilers, heat pumps, and hybrid systems | Thermostat entities for each zone, domestic hot water (DHW) control, and current and target DHW temperature sensors. Some systems also report flow and return temperatures, heating circuit pressure, heat pump mode, heating pump status, or holiday status. |
| **BSB** systems | Thermostat entities for each zone, flame status, and DHW controls and temperature sensors when the system supports DHW. |
| **VELIS** water heaters, including Velis Evo, Velis Lux, Lydos, Lydos Hybrid, and Andris 2 | Power, temperature, and operating mode controls. Depending on the model, you can also get heating status, an Eco switch, or anti-legionella settings. Lydos and Lydos Hybrid expose a current temperature sensor. Lydos Hybrid also supports night mode, permanent boost, and anti-cooling settings. |
| **Nuos Split** heat pump water heater (VELIS Slp) | Water heater controls, a **Plant mode** selector for **Manual** or **Program**, boost, preheating, reduced temperature, and holiday status and end date. |

Earlier versions were tested on the Ariston Alteas One 24, Velis Evo, Velis Lux, and Lydos Hybrid. To see the entities for your installation, open the device from the **Ariston** integration page. Some entities appear after the cloud reports the required data. If an entity is disabled, you can [enable it in Home Assistant](https://www.home-assistant.io/docs/configuration/customizing-entities/#disabling-or-enabling-an-entity).

## Options

Open the **Ariston** integration in **Settings → Devices & services** and select the settings button for your device entry.

| Option | Default | Purpose |
| --- | --- | --- |
| Zone Scan Interval | 180 seconds | How often to check device and zone status. |
| Energy Scan Interval | 60 minutes | How often to retrieve consumption data on devices with metering. |
| Bus Errors Scan Interval | 600 seconds | How often to check for device bus errors. |
| Device rated power (W) | Empty | Electrical power from the device label, used to estimate instantaneous power on supported water heaters. |

## Energy monitoring

- **Consumption (kWh).** Devices with metering can report daily energy use for space heating or hot water, with separate electricity and gas totals where available. Daily totals use the Home Assistant time zone and reset at local midnight. Supported GALEVO systems can also report last month's consumption.
- **Estimated instantaneous power (W).** On Velis Evo, Evo2, Lux, Lydos, and Andris 2, set **Device rated power (W)** to the value on the device label. The sensor reports that value while the heater is heating and 0 W while it is idle. If the rating or heating state is unknown, the sensor reports **Unknown**.

To track electricity use in the Energy dashboard, select an available electricity consumption sensor for the device. If you only have a power sensor, Home Assistant can calculate an energy estimate from it. See [Home Assistant's guide to tracking individual devices](https://www.home-assistant.io/docs/energy/individual-devices/).

## Automation actions

Use the device entities in Home Assistant dashboards, scripts, and automations. The integration also provides these actions in **Developer tools → Actions** when a supported device is set up.

| Action | What it does |
| --- | --- |
| `ariston.create_vacation` | Schedule a holiday on a GALEVO or Nuos Split device. Select the device and enter an end date. Leave the end date empty to clear the holiday. |
| `ariston.set_item_by_id` | Set an Ariston device or thermostat property on a GALEVO system. |

## Support

- If your device is missing during setup, check that it appears in the Ariston NET app under the same account.
- For setup questions or help with an unsupported model, see the [wiki](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/wiki) and [GitHub Discussions](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/discussions).
- Before you report a bug or request a feature, search the [existing issues](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/issues), including closed issues. In a [new issue](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/issues/new/choose), include your Home Assistant version, integration version, and the model shown under **Device info**. Remove account details, device identifiers, and tokens from logs before sharing them. See [how to collect debug logs](https://www.home-assistant.io/docs/configuration/troubleshooting/#enabling-debug-logging).

## Contributing

### Co-maintainers wanted

The project is looking for co-maintainers or a new lead maintainer to triage issues, test and review pull requests, and maintain the integration. If you are interested, [email the maintainer](mailto:fustom@gmail.com) with a short introduction and the areas where you can help.

### Tests

Run the test suite on Linux with Python 3.14.2 to match CI. The suite uses Home Assistant's pytest fixtures and reports line coverage for the integration.

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements_test.txt
python -m pytest
```

To update test dependencies, edit `requirements_test.in` and regenerate the lock file with hashes.

```sh
uv pip compile requirements_test.in --python 3.14.2 --python-version 3.14.2 --universal --generate-hashes --upgrade --output-file requirements_test.txt
```

This project was inspired by [chomupashchuk's Ariston integration](https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2). It uses the [MIT License](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/blob/main/LICENSE).
