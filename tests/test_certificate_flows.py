"""Config-flow certificate confirmation and the reauth flow (audit H2, F1)."""

from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.proxmox_sensors.const import DOMAIN

FP_OLD = "11" * 32
FP_NEW = "22" * 32
FLOW = "custom_components.proxmox_sensors.config_flow"


async def _to_pbs_credentials(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.0.2.20", "platform_type": "PBS"}
    )
    assert result["step_id"] == "credentials_pbs"
    return result


PBS_INPUT = {"user": "ha@pbs", "token_id": "ha", "token_secret": "tok", "verify_ssl": False}


async def test_certificate_is_confirmed_before_credentials_are_used(hass):
    validate = AsyncMock(return_value={"has_minimum": False, "has_all": False})
    with patch(f"{FLOW}.fetch_certificate_fingerprint", return_value=FP_NEW), \
         patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", validate):
        result = await _to_pbs_credentials(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], PBS_INPUT)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "confirm_certificate"
        assert result["description_placeholders"]["fingerprint"].startswith("22:22:")
        validate.assert_not_awaited()  # nothing was sent before the user confirmed

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"confirm": True})
        validate.assert_awaited_once()
        client = validate.await_args.args[0]
        assert client._cert_fingerprint == FP_NEW
        assert result["errors"] == {"base": "insufficient_permissions"}


async def test_rejecting_the_certificate_aborts(hass):
    validate = AsyncMock()
    with patch(f"{FLOW}.fetch_certificate_fingerprint", return_value=FP_NEW), \
         patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", validate):
        result = await _to_pbs_credentials(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], PBS_INPUT)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"confirm": False})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "certificate_rejected"
    validate.assert_not_awaited()


async def test_verified_tls_skips_pinning(hass):
    validate = AsyncMock(return_value={"has_minimum": False, "has_all": False})
    fetch = patch(f"{FLOW}.fetch_certificate_fingerprint")
    with fetch as fetch_mock, patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", validate):
        result = await _to_pbs_credentials(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**PBS_INPUT, "verify_ssl": True}
        )
    fetch_mock.assert_not_called()
    validate.assert_awaited_once()
    assert validate.await_args.args[0]._cert_fingerprint is None


async def test_reauth_accepts_new_certificate_and_secret(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3,
        data={"platform_type": "PBS", "host": "192.0.2.20", "user": "ha@pbs",
              "token_id": "ha", "token_secret": "old", "verify_ssl": False,
              "cert_fingerprint": FP_OLD, "node": "pbs", "server_id": "pbs_1"},
    )
    entry.add_to_hass(hass)
    validate = AsyncMock(return_value={"has_minimum": True, "has_all": True})
    with patch(f"{FLOW}.fetch_certificate_fingerprint", return_value=FP_NEW), \
         patch(f"{FLOW}.ProxmoxConfigFlow._validate_connection", validate), \
         patch("custom_components.proxmox_sensors.async_setup_entry", return_value=True):
        result = await entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"
        assert result["description_placeholders"]["new_fingerprint"].startswith("22:22:")

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token_secret": "new"}
        )
        assert result["errors"] == {"base": "certificate_not_accepted"}
        validate.assert_not_awaited()

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token_secret": "new", "accept_certificate": True}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["cert_fingerprint"] == FP_NEW
    assert entry.data["token_secret"] == "new"
