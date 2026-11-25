"""Manifest metadata checks."""

import json
from pathlib import Path

MANIFEST = Path(__file__).parents[1] / "custom_components" / "proxmox_sensors" / "manifest.json"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_points_at_the_fork():
    """HACS users of the fork must land on the fork's docs and issue tracker."""
    manifest = _manifest()
    assert manifest["issue_tracker"] == "https://github.com/darthrater78/proxmox_sensors/issues"
    assert manifest["documentation"].startswith("https://github.com/darthrater78/proxmox_sensors")
    assert manifest["codeowners"] == ["@darthrater78"]
