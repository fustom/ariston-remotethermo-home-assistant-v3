# Issue #534 implementation checklist

## 1. Let metered devices load during an energy outage

- [x] Add a Lydos Hybrid Home Assistant integration regression for an energy `ConnectionException(500)` at startup and during polling. Assert that the config entry stays loaded, the primary coordinator succeeds, and only the energy coordinator becomes unavailable.
- [x] Use ordinary coordinator refresh for the initial energy fetch in `custom_components/ariston/__init__.py`.
- [x] Verify that the energy sensor becomes available after a successful poll, primary refresh failures still block setup, and devices without metering still skip the energy fetch.
- [x] Run focused and full tests. All 5 focused tests pass. The integration test file has 14 passes and one pre-existing Windows failure. The full suite has 84 passes and two pre-existing device-registry failures. Both failures reproduce on the unmodified baseline.

## 2. Verify Genus One compatibility

- [ ] Check the v0.20.6 thermostat failure on Core 2026.10.2 against the missing legacy temperature property addressed by PR #542.
- [ ] Verify that a build containing #542 registers the same entity and reports its temperature fields on Core 2026.10.2. Confirm the native temperature properties still work on Core 2026.11.1.

## 3. Verify GALEVO polling

- [ ] Compare v0.20.5 with `ariston` 0.19.14, v0.20.6 with 0.19.15, and current `main` with 0.19.16 at the same configured intervals. Record the request counts and ordering for features, properties, menus and reports across startup and repeated polls. Use redacted traces and avoid repeated live reloads.
- [ ] If the failure remains reproducible, add a regression in `python-ariston-api` using `tests/test_galevo_device.py` and, for request or backoff changes, `tests/test_rate_limit.py`. Assert a bounded request count, respect for the existing block window and recovery after successful polling. If the fix isolates a menu failure, verify both first refresh without a cache and later refresh with cached menu data. Confirm an actual properties failure still surfaces.
- [ ] Run `python -m unittest discover --start-directory tests` in the API repo for any library change. Verify that a successful state refresh restores affected entities without reloading the integration.

## 4. Verify the release candidate

- [ ] After the energy fix and compatibility check, run the full integration suite with the candidate dependency. Incorporate any verified GALEVO fix before claiming that symptom is resolved.
- [ ] Validate Lydos startup and energy recovery, Genus One entity setup, and GALEVO state polling on the reported Home Assistant versions. Record the release version and the outcome for each scenario.
