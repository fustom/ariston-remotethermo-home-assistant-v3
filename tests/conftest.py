"""Shared fixtures for Ariston integration tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ariston.const import SystemType, WheType

from custom_components.ariston.coordinator import DeviceDataUpdateCoordinator


@pytest.fixture
def ariston_device():
    """Return a simple device with the identity fields used by entities."""
    return SimpleNamespace(
        name="Test boiler",
        gateway="gateway-1",
        serial_number="serial-1",
        firmware_version="1.0",
        system_type=SystemType.GALEVO,
        whe_type=WheType.Unknown,
        whe_model_type=0,
    )


@pytest.fixture
def coordinator(hass, ariston_device):
    """Return a coordinator backed by a fake Ariston device."""
    coordinator = DeviceDataUpdateCoordinator(
        hass,
        ariston_device,
        300,
        "test",
        AsyncMock(),
    )
    coordinator.async_request_refresh = AsyncMock()
    return coordinator
