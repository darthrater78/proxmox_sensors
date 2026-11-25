"""Shared fixtures for the Proxmox Extended Sensors test suite."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/proxmox_sensors in every test."""
    yield
