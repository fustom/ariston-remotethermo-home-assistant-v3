# Fix plan for Ariston issue #534

## Status

The latest stable integration release is v0.20.6. Current upstream `main` still requires the first energy refresh to succeed before it forwards entity platforms. In Home Assistant, this call raises `ConfigEntryNotReady` when the refresh fails. A persistent HTTP 500 from `consSequencesApi8` can therefore keep a metered device in setup retry after its main state has loaded. The Lydos Hybrid reporter recovered after resetting the heater and reported that controls had also failed in Ariston NET. The cause of the cloud response remains unverified. [Issue #534](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/issues/534) · [Current setup code](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/blob/537564ea594475f205191904b1d4e6a5270f62fc/custom_components/ariston/__init__.py#L132-L147) · [Home Assistant coordinator](https://github.com/home-assistant/core/blob/2026.11.1/homeassistant/helpers/update_coordinator.py#L305-L351)

PR #542 restored the legacy temperature properties on `main` after v0.20.6. This is a confirmed fix for the Home Assistant Core pre-2026.11 compatibility error in #536 and a likely match for the Genus One report on Core 2026.10.2. Confirm that match with the original traceback or an upgrade test on Core 2026.10.2. [PR #542](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/542) · [Genus One report](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/issues/534#issuecomment-6941983856)

The GALEVO report shows HTTP 429 on the state coordinator's menu request. The published Python wheels for `ariston` 0.19.14, 0.19.15 and 0.19.16 all have 429 backoff. The 0.19.15 wheel adds timeout fallback for property batches, and 0.19.16 changes GALEVO menu requests. The 0.19.16 wheel still propagates a menu 429 after API retries are exhausted. The rollback report shows improved availability, with the rate-limit trigger still unverified. [GALEVO report](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/issues/534#issuecomment-6944017110) · [ariston 0.19.15](https://pypi.org/project/ariston/0.19.15/) · [ariston 0.19.16](https://pypi.org/project/ariston/0.19.16/)

## Implementation order

1. Let setup continue after an energy refresh failure. Reuse the bus-errors coordinator's `async_refresh()` pattern in `custom_components/ariston/__init__.py` for the initial energy fetch. Keep the energy coordinator registered so its entities can recover through normal polling. The primary state refresh remains required for setup.
2. Independently verify the Genus One upgrade on Core 2026.10.2 with the merged compatibility fix. Use signs of a network or coordinator failure to investigate any remaining outage on its own evidence.
3. Compare GALEVO request behavior with the published 0.19.14, 0.19.15 and 0.19.16 packages and identical settings. Capture endpoint, status, duration and request count during setup and successive state polls. Use deterministic mocks for batch timeouts, fallback calls and repeated 429s. If a repeatable regression remains, fix the demonstrated request amplification or isolate the failed menu fetch when the primary properties request succeeds. Reuse the existing API backoff and define whether each menu-backed entity can safely use a cached value or must be unavailable.
4. Verify the candidate integration release. Exercise a metered Lydos setup with an energy outage and recovery, a Genus One upgrade on the affected Core version, and GALEVO on Core 2026.11.1 across several poll cycles. Publish a new API package and update the integration's dependency pins only if the confirmed GALEVO fix requires a library change.

The [task checklist](todo.md) records the tests and acceptance criteria.

## Verification during planning

The current Python API checkout passed all 96 unit tests. The Home Assistant setup behavior was traced against the Core 2026.11.1 coordinator source. Live devices and the Home Assistant test suite were outside this planning check.

## Implementation progress

Completed the initial energy refresh isolation and added a real Home Assistant config-entry test for a Lydos Hybrid energy HTTP 500 at startup and during polling. All 5 focused tests pass. The full integration test file has 14 passing tests and one pre-existing Windows failure. The full test suite has 84 passing tests and two pre-existing device-registry failures. Both failures also occur on the unmodified baseline. The GALEVO recovery integration test passes. The Genus One Core 2026.10.2 check and live-device checks remain pending.
