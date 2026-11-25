"""Authorization and validation of the integration's domain services (audit H1/M5)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.proxmox_sensors.const import DOMAIN
from custom_components.proxmox_sensors.services import (
    node_controls_enabled,
    register_services,
)

NODE = "pve1"


def _pve_entry(hass, **data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"platform_type": "PVE", "node": NODE, "host": "192.0.2.10", **data},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def client():
    client = MagicMock()
    client.shutdown_node = AsyncMock(return_value="UPID:ok")
    client.reboot_node = AsyncMock(return_value="UPID:ok")
    client.start_vzdump = AsyncMock(return_value="UPID:backup")
    return client


def _load(hass, entry, client):
    """Mark an entry as loaded the way async_setup_entry does, without network."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "services_ready": True,
        "client": client,
        "coordinator": MagicMock(data={}),
    }
    register_services(hass, entry)


@pytest.mark.parametrize(
    ("data", "options", "expected"),
    [
        ({}, {}, False),  # never opted in: disabled
        ({"enable_node_controls": True}, {}, True),
        ({"enable_node_controls": True}, {"enable_node_controls": False}, False),
        ({}, {"enable_node_controls": True}, True),
    ],
)
def test_node_controls_default_off(hass, data, options, expected):
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=options)
    assert node_controls_enabled(entry) is expected


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("confirm_shutdown_node", {"node": NODE, "confirm": True}),
        ("confirm_reboot_node", {"node": NODE, "confirm": True}),
        ("create_vzdump_backup", {"node": NODE, "storage": "local", "guests": "100"}),
        ("backup_all", {"node": NODE, "storage": "local", "include_vms": True}),
        ("wake_node", {"node": NODE, "mac": "AA:BB:CC:DD:EE:FF"}),
    ],
)
async def test_non_admin_cannot_call_services(hass, hass_read_only_user, client, service, data):
    entry = _pve_entry(hass, enable_node_controls=True)
    _load(hass, entry, client)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, service, data,
            blocking=True, context=Context(user_id=hass_read_only_user.id),
        )
    client.shutdown_node.assert_not_awaited()
    client.reboot_node.assert_not_awaited()
    client.start_vzdump.assert_not_awaited()


@pytest.mark.parametrize(
    ("service", "method"),
    [("confirm_shutdown_node", "shutdown_node"), ("confirm_reboot_node", "reboot_node")],
)
async def test_power_services_respect_disabled_node_controls(
    hass, hass_admin_user, client, service, method
):
    entry = _pve_entry(hass)  # enable_node_controls never set
    _load(hass, entry, client)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, service, {"node": NODE, "confirm": True},
            blocking=True, context=Context(user_id=hass_admin_user.id),
        )
    getattr(client, method).assert_not_awaited()


@pytest.mark.parametrize(
    ("service", "method"),
    [("confirm_shutdown_node", "shutdown_node"), ("confirm_reboot_node", "reboot_node")],
)
async def test_power_services_run_for_admin_when_enabled(
    hass, hass_admin_user, client, service, method
):
    entry = _pve_entry(hass, enable_node_controls=True)
    _load(hass, entry, client)
    context = Context(user_id=hass_admin_user.id)

    await hass.services.async_call(DOMAIN, service, {"node": NODE}, blocking=True, context=context)
    getattr(client, method).assert_not_awaited()  # first call only asks for confirmation

    await hass.services.async_call(
        DOMAIN, service, {"node": NODE, "confirm": True}, blocking=True, context=context
    )
    getattr(client, method).assert_awaited_once_with(hass, NODE)


@pytest.mark.parametrize(
    "data",
    [
        {"node": NODE, "storage": "local", "guests": "100", "mode": "rm -rf"},
        {"node": NODE, "storage": "local", "guests": "100", "max_concurrent": 0},
        {"node": NODE, "storage": "local", "guests": "100", "delay_between": -1},
        {"storage": "local", "guests": "100"},  # node is required
    ],
)
async def test_backup_service_rejects_invalid_input(hass, hass_admin_user, client, data):
    entry = _pve_entry(hass)
    _load(hass, entry, client)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "create_vzdump_backup", data,
            blocking=True, context=Context(user_id=hass_admin_user.id),
        )
    client.start_vzdump.assert_not_awaited()


@pytest.mark.parametrize("mac", ["AA:BB:CC:DD:EE", "not-a-mac-address", "AA:BB:CC:DD:EE:FF:00"])
async def test_wake_node_rejects_invalid_mac(hass, hass_admin_user, client, mac):
    entry = _pve_entry(hass)
    _load(hass, entry, client)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "wake_node", {"node": NODE, "mac": mac},
            blocking=True, context=Context(user_id=hass_admin_user.id),
        )
