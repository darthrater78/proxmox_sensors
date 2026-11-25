# Changelog

All notable changes to this fork are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This fork uses date
versions (`YYYY.M.D`, or `YYYY.M.D.N` for a later release on the same day).
Releases before the fork are listed in the
[upstream project](https://github.com/Javisen/proxmox_sensors/releases).

## [Unreleased]

### Security
- Proxmox certificates are no longer accepted blindly when "Verify SSL
  Certificate" is off: the certificate's SHA-256 fingerprint is pinned,
  confirmed by you during setup before any credential is sent, and enforced on
  every request including the password login. Existing entries pin on their
  next start and show the fingerprint in a notification.
- Domain services that back up guests, wake, reboot or shut down nodes now
  require a Home Assistant administrator and validate their input.
- Node reboot and shutdown services now honour the node-controls setting, and
  node control buttons are no longer created for entries that never opted in.

### Added
- Reauthentication flow: a rotated password or token, or a changed server
  certificate, now opens a prompt instead of requiring the entry to be deleted.
- CI for the fork: hassfest and HACS validation, ruff, pytest with the Home
  Assistant test harness, shellcheck, and actionlint for the workflows.
- Release workflow: publishes only from tags on `main` whose commit passed CI
  and whose `manifest.json` version matches the tag, and attaches the sidecar
  and installer with `SHA256SUMS` and a signed build-provenance attestation.
- CodeQL scanning, dependency review on pull requests, a weekly `pip-audit`
  report, and Dependabot for GitHub Actions and Python dependencies.
- Security architecture section in the README.

### Changed
- `manifest.json`, the README and the issue template point at this fork
  instead of upstream; HACS installs it as a custom repository.

### Removed
- The upstream documentation website (Astro, GitHub Pages, `CNAME` for
  upstream's domain) and its npm toolchain, which also removes five High npm
  advisories from the repository.
- The upstream issue bot that auto-closed issues after three days.
- Dead code found by the new lint: an unused `limited_task_func` that referred
  to an undefined name, a shadowed duplicate of
  `build_cluster_notifications_data`, and unused imports and variables.
