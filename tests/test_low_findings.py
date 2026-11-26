"""Audit L1-L3, L5, L6: error disclosure, swallowed errors, status guessing,
dependency bounds and disks woken by the SMART scan."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from proxmoxer.core import AuthenticationError as ProxmoxerAuthenticationError

from custom_components.proxmox_sensors import api
from custom_components.proxmox_sensors.logic.smart_cache import SmartCache
from test_sidecar import sidecar

MANIFEST = Path(__file__).parents[1] / "custom_components" / "proxmox_sensors" / "manifest.json"
SECRET = "serial WD-XYZ123 at /dev/disk/by-id/ata-secret"


def _handler(path="/memory"):
    """A Handler that records what it would send, with no socket behind it."""
    handler = sidecar.Handler.__new__(sidecar.Handler)
    handler.path = path
    handler.sent = []
    handler._send_status_json = lambda code, error, extra_headers=(): handler.sent.append(
        (code, error)
    )
    return handler


# ----- L1: no exception text or stderr in responses --------------------------

def test_error_response_keeps_details_out_of_the_body(capsys):
    handler = _handler("/memory?x=1")
    handler._send_error_response("dmidecode failed", f"{SECRET}\nsecond line")
    assert handler.sent == [(500, "dmidecode failed")]
    log = capsys.readouterr().err
    assert SECRET in log and "/memory: dmidecode failed" in log
    assert "\n" not in log.rstrip("\n")  # one journal line, control chars removed


@pytest.mark.parametrize("method, endpoint", [
    ("_handle_memory", "Error getting memory info"),
    ("_handle_mounts", "Error getting mount info"),
])
def test_handlers_do_not_echo_exceptions(monkeypatch, capsys, method, endpoint):
    def boom(*args, **kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(sidecar.subprocess, "run", boom)
    handler = _handler()
    getattr(handler, method)()
    assert handler.sent == [(500, endpoint)]
    assert SECRET in capsys.readouterr().err


def test_command_stderr_is_not_echoed(monkeypatch, capsys):
    monkeypatch.setattr(sidecar.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1, stdout="", stderr=SECRET,
    ))
    handler = _handler()
    handler._handle_memory()
    assert handler.sent == [(500, "dmidecode failed")]
    assert SECRET in capsys.readouterr().err


def test_failed_smart_scan_payload_is_generic(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(sidecar.subprocess, "run", boom)
    assert _handler()._get_smart_data_fast() == {"error": "SMART scan failed"}


# ----- L2: failures are logged, not silently dropped -------------------------

def test_disk_query_failure_is_logged(monkeypatch, capsys):
    def denied(*args, **kwargs):
        raise PermissionError("smartctl: permission denied")

    monkeypatch.setattr(sidecar.subprocess, "run", denied)
    assert _handler()._get_disk_info_safe("/dev/sda", "sat") is None
    assert "SMART query for /dev/sda failed" in capsys.readouterr().err


def test_no_bare_except_left_in_the_sidecar():
    source = Path(sidecar.__file__).read_text(encoding="utf-8")
    assert "except:" not in source
    assert "except Exception:\n            pass" not in source


# ----- L3: status codes come from the error, never its message ---------------

@pytest.mark.parametrize("message", [
    "VM 401 does not exist", "storage local-403 is full", "timed out after 4013 ms",
])
def test_numbers_in_messages_are_not_status_codes(message):
    assert api._extract_status_code(RuntimeError(message)) is None


def test_login_failures_are_auth_failures():
    native = ProxmoxerAuthenticationError("Couldn't authenticate user: root@pam to https://h")
    assert api._extract_status_code(native) == 401
    assert api._extract_status_code(api._TicketRejected("refused", 401)) == 401
    assert api._extract_status_code(api._TicketRejected("server error", 500)) == 500


def test_build_error_from_a_wrong_password_asks_for_reauth():
    client = api.ProxmoxClient(host="192.0.2.10", user="root@pam", password="x")
    client._build_error = api._TicketRejected("refused", 401)
    with pytest.raises(api.AuthenticationError):
        client._raise_build_error("nodes")


# ----- L5: dependency upper bound --------------------------------------------

def test_proxmoxer_requirement_is_bounded():
    requirements = json.loads(MANIFEST.read_text(encoding="utf-8"))["requirements"]
    assert "proxmoxer>=2.0.0,<3" in requirements


# ----- L6: the full SMART scan never wakes a sleeping disk -------------------

def test_scan_reports_standby_instead_of_waking(monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=3, stdout="", stderr="")

    monkeypatch.setattr(sidecar.subprocess, "run", run)
    info = _handler()._get_disk_info_safe("/dev/sdb", "sat")
    assert info["standby"] is True and info["smart_available"] is False
    assert calls == [["smartctl", "-a", "-d", "sat", "-n", "standby,3", "-j", "/dev/sdb"]]


def test_extended_scan_skips_standby_disks(monkeypatch):
    handler = _handler()
    monkeypatch.setattr(handler, "_get_smart_data_fast", lambda: {
        "sdb": {"standby": True, "smart_available": False},
    })
    monkeypatch.setattr(handler, "_get_detailed_smart_attributes",
                        lambda device: pytest.fail("woke a standby disk"))
    assert handler._get_smart_data_extended()["sdb"]["standby"] is True


def test_cache_keeps_last_reading_for_a_sleeping_disk():
    cache = SmartCache(5)
    awake = {"sda": {"temperature": 30}, "sdb": {"temperature": 35}}
    assert cache.accept(awake, 0)
    assert cache.accept({"sda": {"temperature": 31}, "sdb": {"standby": True}}, 300)
    assert cache.snapshot("pve") == {"pve": {"sda": {"temperature": 31},
                                             "sdb": {"temperature": 35}}}


def test_cache_shows_standby_for_a_disk_never_seen_awake():
    cache = SmartCache(5)
    assert cache.accept({"sdc": {"standby": True}}, 0)
    assert cache.snapshot("pve") == {"pve": {"sdc": {"standby": True}}}

