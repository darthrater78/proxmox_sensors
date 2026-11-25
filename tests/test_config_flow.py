"""Config flow entry-point tests."""

import pytest

from homeassistant.data_entry_flow import FlowResultType

from custom_components.proxmox_sensors.config_flow import _config_host_error
from custom_components.proxmox_sensors.const import DOMAIN


@pytest.mark.parametrize(
    ("host", "platform", "expected"),
    [
        ("192.168.1.10", "PVE", None),
        ("pve.example.lan", "PVE", None),
        ("[fd00::10]", "PVE", None),
        ("[fd00::10]", "PBS", "ipv6_not_supported"),
        ("https://pve.example.lan", "PVE", "invalid_host"),
        ("pve.example.lan/api", "PVE", "invalid_host"),
        ("user@pve.example.lan", "PVE", "invalid_host"),
        ("", "PVE", "invalid_host"),
        ("bad host", "PVE", "invalid_host"),
    ],
)
def test_config_host_error(host, platform, expected):
    assert _config_host_error(host, platform) == expected


async def test_user_step_shows_form(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_rejects_url_as_host(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "https://pve.example.lan", "platform_type": "PVE"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"host": "invalid_host"}
