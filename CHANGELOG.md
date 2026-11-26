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
- The hardware sidecar now serves HTTPS with a self-signed certificate that
  Home Assistant pins, and requires a random bearer token on every request.
  Clients outside its allow-list are dropped before the TLS handshake and
  blocked by systemd as well. It serves at most 8 requests at once, gives a
  client 15 seconds to send its request, and runs in a tighter systemd
  sandbox.
- The sidecar installer downloads from this fork's releases and installs the
  sidecar only if it matches the release's `SHA256SUMS`. It no longer
  downloads from upstream's `main` branch.
- Sidecar error responses no longer include exception text or command
  output, which could reveal device paths and serial numbers; the details
  are written to the node's journal instead.

### Added
- Reauthentication flow: a rotated password or token, or a changed server
  certificate, now opens a prompt instead of requiring the entry to be deleted.
- Reconfigure: change an entry's host, user, sign-in method, secrets and
  certificate checking in place. The server must be the same machine (same PVE
  node, PBS instance or cluster name); a new host re-confirms its certificate.
- PBS options: choose which datastores are monitored. Newly created
  datastores are monitored automatically; deselected ones are removed with
  their buttons and devices.
- Cluster options: switch the backup, failed-task, firewall and HA sensor
  groups on or off.
- PVE options: switches for memory-module, backup-progress, storage-list and
  nodes-list sensors, which existed but could not be changed.
- Sidecar settings on the PVE Reconfigure page (token and certificate
  fingerprint). They are checked against the sidecar before they are saved.
- Repair issues for a sidecar that uses plain HTTP, presents a changed
  certificate, or rejects the token.
- Sidecar installer options: `--version`, `--local`, `--allowed-ips`
  (non-interactive), `--rotate-token`, `--rotate-cert`, `--legacy-http`.
- CI for the fork: hassfest and HACS validation, ruff, pytest with the Home
  Assistant test harness, shellcheck, and actionlint for the workflows.
- Release workflow: publishes only from tags on `main` whose commit passed CI
  and whose `manifest.json` version matches the tag, and attaches the sidecar
  and installer with `SHA256SUMS` and a signed build-provenance attestation.
- CodeQL scanning, dependency review on pull requests, a weekly `pip-audit`
  report, and Dependabot for GitHub Actions and Python dependencies.
- Security architecture section in the README.

### Fixed
- The VM/CT selection on the options page no longer disappears when another
  node in the cluster is offline; that node's guests come from the cluster
  inventory.
- Saving the PBS or cluster options page no longer erases other stored
  options, such as the PBS prune and sync job mappings.
- A stale stored option can no longer silently override a PVE setting just
  saved on the options page.
- Wake-on-LAN MAC addresses are validated on the PVE and PBS options pages.
- The sidecar's full SMART scan no longer spins up sleeping disks; a disk in
  standby keeps its last reading in Home Assistant.
- An error message that merely contained "401" or "403" (a VM ID, a storage
  name) no longer counts as an authentication failure and starts a
  reauthentication prompt.
- A rejected password now starts the reauthentication prompt instead of
  showing the server as unreachable.
- Sidecar errors that were silently ignored are now logged to the journal.

### Changed
- **Re-running the sidecar installer switches the sidecar to HTTPS with a
  token.** Afterwards, enter the token and certificate fingerprint it prints
  on the PVE entry's Reconfigure page. Until then that node's hardware sensors
  are unavailable. `--legacy-http` keeps the old plain-HTTP mode; Home
  Assistant shows a repair warning while a sidecar uses it.
- `manifest.json`, the README and the issue template point at this fork
  instead of upstream; HACS installs it as a custom repository.
- `proxmoxer` is limited to the 2.x series it is tested with.

### Removed
- The upstream documentation website (Astro, GitHub Pages, `CNAME` for
  upstream's domain) and its npm toolchain, which also removes five High npm
  advisories from the repository.
- The upstream issue bot that auto-closed issues after three days.
- Dead code found by the new lint: an unused `limited_task_func` that referred
  to an undefined name, a shadowed duplicate of
  `build_cluster_notifications_data`, and unused imports and variables.
