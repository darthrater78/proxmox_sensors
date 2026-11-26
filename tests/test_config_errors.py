"""Connection-check failures map to the right form error in reauth and reconfigure."""

import pytest

from custom_components.proxmox_sensors.api import (
    AuthenticationError,
    CannotConnect,
    CertificateMismatchError,
    CertificateNotPinned,
    PermissionError as ProxmoxPermissionError,
)
from custom_components.proxmox_sensors.config_flow import _connection_error_key


@pytest.mark.parametrize("err, key", [
    # A changed certificate is an AuthenticationError subclass; it must not
    # read as a wrong password.
    (CertificateMismatchError("changed"), "certificate_changed"),
    (AuthenticationError("bad password"), "invalid_auth"),
    (ProxmoxPermissionError("no Sys.Audit"), "insufficient_permissions"),
    (CannotConnect("down"), "cannot_connect"),
    (CertificateNotPinned("no pin"), "cannot_connect"),
])
def test_known_failures(err, key):
    assert _connection_error_key(err, "reauthentication") == key


def test_unexpected_failure_is_logged_as_unknown(caplog):
    assert _connection_error_key(RuntimeError("boom"), "reconfiguration") == "unknown"
    assert "Unexpected error during reconfiguration" in caplog.text
