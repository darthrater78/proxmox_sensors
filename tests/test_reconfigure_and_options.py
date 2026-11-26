"""Reconfigure flow and options pages (audit F1-F5)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.proxmox_sensors.api import CannotConnect
from custom_components.proxmox_sensors.const import DOMAIN
from custom_components.proxmox_sensors.logic.entry_options import (
    entry_option,
    monitored_pbs_datastores,
)

FLOW = "custom_components.proxmox_sensors.config_flow"
FP_OLD = "11" * 32
FP_NEW = "22" * 32
VALID = {"has_minimum": True, "has_all": True}


def _pve_entry(hass, **extra):
    data = {
        "platform_type": "PVE", "host": "192.0.2.10", "node": "pve1", "user": "root@pam",
        "password": "old-password", "verify_ssl": False, "cert_fingerprint": FP_OLD,
        "server_id": "pve1", **extra,
    }
    entry = MockConfigEntry(domain=DOMAIN, version=3, data=data, unique_id="pve:192.0.2.10:pve1")
    entry.add_to_hass(hass)
    return entry


def _schema_options(result, key):
    for marker, validator in result["data_schema"].schema.items():
        if str(marker) == key:
            return getattr(validator, "options", None)
    raise AssertionError(f"{key} not in form")


# ----- reconfigure -------------------------------------------------------

async def test_reconfigure_new_host_confirms_certificate_and_keeps_password(hass):
    entry = _pve_entry(hass)
    validate = AsyncMock(return_value=VALID)
    get = AsyncMock(return_value=[{"node": "pve1"}, {"node": "pve2"}])
    with patch(f"{FLOW}.fetch_certificate_fingerprint", return_value=FP_NEW), \
         patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", validate), \
         patch(f"{FLOW}.ProxmoxClient.get", get), \
         patch("custom_components.proxmox_sensors.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "host": "192.0.2.99", "user": "root@pam", "use_token": False, "verify_ssl": False,
        })
        assert result["step_id"] == "confirm_certificate"
        validate.assert_not_awaited()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"confirm": True})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "192.0.2.99"
    assert entry.data["password"] == "old-password"  # blank field kept the secret
    assert entry.data["cert_fingerprint"] == FP_NEW
    assert entry.data["node"] == "pve1"
    assert entry.unique_id == "pve:192.0.2.99:pve1"


async def test_reconfigure_rejects_server_without_the_node(hass):
    entry = _pve_entry(hass)
    with patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", AsyncMock(return_value=VALID)), \
         patch(f"{FLOW}.ProxmoxClient.get", AsyncMock(return_value=[{"node": "other"}])):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "host": "192.0.2.10", "user": "root@pam", "use_token": False, "verify_ssl": False,
        })
    assert result["errors"] == {"base": "node_not_found"}
    assert entry.data["host"] == "192.0.2.10"


async def test_reconfigure_switch_to_token_requires_secret(hass):
    entry = _pve_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "host": "192.0.2.10", "user": "root@pam", "use_token": True, "token_id": "ha",
        "verify_ssl": False,
    })
    assert result["errors"] == {"base": "secret_required"}


async def test_reconfigure_switch_to_token_drops_password(hass):
    entry = _pve_entry(hass)
    with patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", AsyncMock(return_value=VALID)), \
         patch(f"{FLOW}.ProxmoxClient.get", AsyncMock(return_value=[{"node": "pve1"}])), \
         patch("custom_components.proxmox_sensors.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "host": "192.0.2.10", "user": "root@pam", "use_token": True, "token_id": "ha",
            "token_secret": "tok", "verify_ssl": False,
        })
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert "password" not in entry.data
    assert entry.data["token_secret"] == "tok"
    assert entry.data["cert_fingerprint"] == FP_OLD  # same host: pin unchanged


async def test_reconfigure_pbs_refuses_a_different_instance(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={
        "platform_type": "PBS", "host": "192.0.2.20", "user": "ha@pbs", "token_id": "ha",
        "token_secret": "tok", "verify_ssl": True, "pbs_instance_id": "instance-a",
        "node": "pbs", "server_id": "pbs_1",
    })
    entry.add_to_hass(hass)
    with patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", AsyncMock(return_value=VALID)), \
         patch(f"{FLOW}.ProxmoxClient.get_pbs_instance_id", AsyncMock(return_value="instance-b")):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "host": "192.0.2.21", "user": "ha@pbs", "token_id": "ha", "verify_ssl": True,
        })
    assert result["errors"] == {"base": "different_server"}
    assert entry.data["host"] == "192.0.2.20"


# ----- options -----------------------------------------------------------

def test_entry_option_precedence():
    entry = MockConfigEntry(domain=DOMAIN, data={"a": 1, "b": 2}, options={"a": 3})
    assert entry_option(entry, "a") == 3
    assert entry_option(entry, "b") == 2
    assert entry_option(entry, "c", True) is True


def test_monitored_datastores_keep_new_ones():
    entry = MockConfigEntry(domain=DOMAIN, options={"excluded_datastores": ["old"]})
    assert monitored_pbs_datastores(entry, {"old": 1, "new": 2}) == {"new": 2}


async def test_pbs_options_exclude_datastores_and_keep_other_options(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={
        "platform_type": "PBS", "host": "192.0.2.20", "node": "pbs", "server_id": "pbs_1",
        "verify_ssl": True,
    }, options={"pbs_prune_jobs_by_datastore": {"s1": "job1"}})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": MagicMock(data={"pbs_datastores": {"s1": {}, "s2": {}}}),
    }
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert set(_schema_options(result, "datastores")) == {"s1", "s2"}

        bad = await hass.config_entries.options.async_configure(result["flow_id"], {
            "datastores": ["s1"], "enable_pbs_node_controls": True, "wol_mac": "nope",
            "verify_ssl": True,
        })
        assert bad["errors"] == {"wol_mac": "invalid_mac"}

        result = await hass.config_entries.options.async_configure(bad["flow_id"], {
            "datastores": ["s1"], "enable_pbs_node_controls": False,
            "wol_mac": "AA:BB:CC:DD:EE:FF", "verify_ssl": True,
        })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["excluded_datastores"] == ["s2"]
    assert entry.options["pbs_prune_jobs_by_datastore"] == {"s1": "job1"}  # not wiped
    assert entry.options["enable_pbs_node_controls"] is False
    assert entry.data["wol_mac"] == "AA:BB:CC:DD:EE:FF"


async def test_cluster_options_toggle_sensor_groups(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={
        "platform_type": "CLUSTER", "host": "192.0.2.30", "node": "Proxmox", "verify_ssl": True,
    }, options={"keep": "me"})
    entry.add_to_hass(hass)
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {
            "enable_cluster_backups": False, "enable_cluster_failed_tasks": True,
            "enable_cluster_firewall": False, "enable_cluster_ha": True, "verify_ssl": True,
        })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["enable_cluster_backups"] is False
    assert entry.options["enable_cluster_firewall"] is False
    assert entry.options["keep"] == "me"


@pytest.fixture
def cluster_with_offline_node():
    resources = [
        {"type": "node", "node": "pve1", "status": "online"},
        {"type": "node", "node": "pve2", "status": "offline"},
        {"type": "qemu", "node": "pve1", "vmid": 100, "name": "web"},
        {"type": "qemu", "node": "pve2", "vmid": 200, "name": "db"},
        {"type": "lxc", "node": "pve1", "vmid": 300, "name": "dns"},
    ]

    async def fake_get(self, hass, path, raise_errors=False):
        if path == "cluster/resources":
            return resources
        if path == "nodes/pve1/qemu":
            return [{"vmid": 100, "name": "web"}]
        if path == "nodes/pve1/lxc":
            return [{"vmid": 300, "name": "dns"}]
        if path.startswith("nodes/pve2/"):
            raise CannotConnect("node pve2 is offline")
        return []

    return fake_get


async def test_guest_options_survive_an_offline_cluster_node(hass, cluster_with_offline_node):
    entry = _pve_entry(hass, cluster_id="lab")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": MagicMock(data={"cluster_id": "lab", "cluster_nodes": ["pve1", "pve2"]}),
    }
    with patch("custom_components.proxmox_sensors.options_flow.ProxmoxClient.get",
               cluster_with_offline_node):
        result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert not result.get("errors")
    assert set(_schema_options(result, "vms")) == {"100"}  # this node's guests
    assert set(_schema_options(result, "cts")) == {"300"}
    for key in ("enable_memory_monitoring", "enable_backup_progress",
                "enable_storage_list", "enable_nodes_list"):
        assert any(str(marker) == key for marker in result["data_schema"].schema)
