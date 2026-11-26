<p align="center">
  <img src="img/logo_int.png" alt="Proxmox Extended Sensors Logo" width="600"/>
</p>

> **Advanced Proxmox VE, PBS & PDM monitoring, control and dashboard integration for Home Assistant.**

> [!NOTE]
> This is **[darthrater78/proxmox_sensors](https://github.com/darthrater78/proxmox_sensors)**, a security-hardened fork of [Javisen/proxmox_sensors](https://github.com/Javisen/proxmox_sensors). It uses date versions (`YYYY.M.D`) and its own release pipeline.
> **[Release notes for v2026.11.26](https://github.com/darthrater78/proxmox_sensors/releases/tag/v2026.11.26)** · [All releases](https://github.com/darthrater78/proxmox_sensors/releases) · [Changelog](CHANGELOG.md) · [Security architecture](#-security-architecture)

# 🚀 Proxmox Extended Sensors

## 📚 Documentation & Guides

**Select your language to start the installation and configuration:**

[![English](https://img.shields.io/badge/ENGLISH-blue?style=for-the-badge&logo=translate&logoColor=white)](docs/en/README.md)
[![中文](https://img.shields.io/badge/%E4%B8%AD%E6%96%87-blue?style=for-the-badge&logo=translate&logoColor=white)](docs/zh/README.md)
[![Español](https://img.shields.io/badge/ESPA%C3%91OL-orange?style=for-the-badge&logo=translate&logoColor=white)](docs/es/README.md)
[![Italiano](https://img.shields.io/badge/ITALIANO-green?style=for-the-badge&logo=translate&logoColor=white)](docs/it/README.md)
[![Français](https://img.shields.io/badge/FRAN%C3%87AIS-blue?style=for-the-badge&logo=translate&logoColor=white)](docs/fr/README.md)
[![Deutsch](https://img.shields.io/badge/DEUTSCH-red?style=for-the-badge&logo=translate&logoColor=white)](docs/de/README.md)
[![Nederlands](https://img.shields.io/badge/NEDERLANDS-orange?style=for-the-badge&logo=translate&logoColor=white)](docs/nl/README.md)
[![Português](https://img.shields.io/badge/PORTUGU%C3%8AS-green?style=for-the-badge&logo=translate&logoColor=white)](docs/pt/README.md)
[![Русский](https://img.shields.io/badge/%D0%A0%D0%A3%D0%A1%D0%A1%D0%9A%D0%98%D0%99-lightgrey?style=for-the-badge&logo=translate&logoColor=white)](docs/ru/README.md)
[![Українська](https://img.shields.io/badge/%D0%A3%D0%9A%D0%A0%D0%90%D0%87%D0%9D%D0%A1%D0%AC%D0%9A%D0%90-yellow?style=for-the-badge&logo=translate&logoColor=white)](docs/uk/README.md)

---

## 📑 Table of Contents

- [Introduction](#-introduction)
- [Core Features](#-core-features)
- [PVE & CLUSTER Association](#-pve--cluster-association)
- [Dynamic Proxmox Dashboard](#-dynamic-proxmox-dashboard)
- [Migration-Safe VM & LXC Monitoring](#-migration-safe-vm--lxc-monitoring)
- [Resilient Monitoring & Fault Isolation](#%EF%B8%8F-resilient-monitoring--fault-isolation)
- [PVE Replication Status](#-pve-replication-status)
- [Proxmox Datacenter Manager (PDM)](#-proxmox-datacenter-manager-pdm)
- [Proxmox Backup Server (PBS)](#%EF%B8%8F-proxmox-backup-server-pbs)
- [Remote / Hosted PBS](#%EF%B8%8F-remote--hosted-pbs)
- [Multi-PBS Support](#-multi-pbs-support)
- [Hardware Sidecar](#-hardware-sidecar)
- [Sidecar Status](#%EF%B8%8F-sidecar-status)
- [Cluster Monitoring](#-cluster-monitoring)
- [Mounted Disks & Network Storage](#-mounted-disks--network-storage)
- [Hardware & Node Monitoring](#-hardware--node-monitoring)
- [Physical Wake-on-LAN](#-physical-wake-on-lan)
- [Virtual Machines & Containers](#%EF%B8%8F-virtual-machines--containers)
- [Backup Services](#-backup-services-vms--cts)
- [Supported Versions](#-supported-versions)
- [Installation](#-installation)
- [Security Architecture](#-security-architecture)
- [Changelog](CHANGELOG.md)
---

## 🚀 Introduction

**Proxmox Extended Sensors** brings detailed Proxmox VE, Proxmox Backup Server, Proxmox Datacenter Manager and cluster monitoring into Home Assistant, with stable entity identity, hardware telemetry, backup and replication information, maintenance actions and an optional dynamic Lovelace dashboard.

The integration is designed for both standalone Proxmox nodes and multi-node environments. It isolates partial API failures, preserves valid data during temporary outages and tracks VM/LXC guests across correctly associated cluster nodes without tying their logical Home Assistant identity to the physical node currently hosting them.

---

## ✨ Core Features

- 🔗 **PVE ↔ CLUSTER association** — configure a PVE node as standalone or associate it with its corresponding CLUSTER entry.
- 🔄 **Migration-safe VM/LXC identity** — guests can keep their Home Assistant identity when moving between correctly associated nodes.
- 🛡️ **Partial-failure resilience** — a failing API section does not unnecessarily invalidate unrelated data.
- 🔁 **PVE Replication monitoring** — global status plus per-job runtime information.
- 🌐 **PDM centralized monitoring** — overall health, inventory, capacity, updates and per-remote PVE/PBS summaries.
- 🗄️ **PBS monitoring and maintenance** — datastore usage, backups, deduplication, GC, Prune, Verify and Sync where available.
- ☁️ **Remote / hosted PBS connectivity** — standard PBS API connections can also be used with hosted services when the provider exposes the required permissions.
- ❤️ **Sidecar Status** — diagnostic health for Memory, Mounts, Sensors and SMART endpoints.
- 🌡️ **Hardware monitoring** — CPU, temperatures, voltages, fans, NVMe, SMART, DIMM/SMBIOS and Raspberry Pi CPU temperature where exposed.
- ⚡ **Physical Wake-on-LAN** — wake a configured physical PVE node directly from the integration, even while the node is offline.
- 📊 **VM/LXC resource monitoring** — including CT memory/disk and VM memory percentages.
- 🎨 **Dynamic Proxmox Dashboard** — PVE, PBS, CLUSTER and PDM dashboards generated from the resources available in Home Assistant.

> [!CAUTION]
> **Upgrading from an older installation?**
> Re-run the sidecar installer on every PVE node (see [Hardware Sidecar](#-hardware-sidecar)) so its endpoints stay aligned with the integration and it switches to HTTPS with a token.

---

## 🔌 Hardware Sidecar

Temperatures, fans, SMART, memory modules, mounts and KSM come from a small optional service on each PVE node, `pve-sensors-api.py`, listening on port 9000. Install or update it as root on the node:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

The installer:

- asks which Home Assistant IP addresses may connect (or pass `--allowed-ips 192.0.2.50`);
- downloads `pve-sensors-api.py` from this fork's latest release and refuses to install it unless it matches the release's `SHA256SUMS` (`--version TAG` installs a specific release, `--local DIR` a copy you downloaded and checked yourself);
- generates a self-signed certificate and a random token (both kept on re-runs; `--rotate-cert` / `--rotate-token` replace them);
- installs a sandboxed systemd service that only the allowed addresses can reach, and prints the **token** and the **certificate SHA-256 fingerprint**.

Then, in Home Assistant, open the node's Proxmox entry → **⋮ → Reconfigure** and enter the **Sidecar token** and **Sidecar certificate SHA-256**. Home Assistant checks them against the sidecar before saving, and from then on sends requests only to that exact certificate.

`--legacy-http` keeps the old plain-HTTP, IP-only behaviour for integration versions without token support. While a sidecar answers over plain HTTP, Home Assistant shows a **repair warning** for that entry; a changed sidecar certificate or a rejected token shows a repair error instead.

---

## 🔗 PVE & CLUSTER Association

A PVE connection can operate as an **independent node** or be explicitly associated with a configured **CLUSTER** entry.

The association uses a persistent internal scope instead of relying only on node or cluster names. This keeps separate Proxmox environments isolated and gives the integration a stable context for guest identity and reconciliation.

When configuring a new PVE entry, choose the matching CLUSTER when the node belongs to a cluster already configured in Home Assistant. Choose standalone mode when the PVE node should be managed independently.

Existing installations are handled conservatively: legacy identities are preserved where required instead of being forcibly converted when the association cannot be determined safely.

---

## 🎨 Dynamic Proxmox Dashboard

The optional dashboard system builds a complete Lovelace starting point from the entities and resources discovered in your installation.

### Available dashboard types

- **PVE** — node health, temperatures, node information, storage, CTs, VMs, diagnostics and replication.
- **PBS** — server/datastore information, backups, maintenance, tasks and actions.
- **CLUSTER** — cluster health, resources, system state, backup health and replication.
- **PDM** — centralized infrastructure status, inventory, capacity, updates and configured remotes.

When multiple PBS or CLUSTER instances are configured, the dashboard keeps each instance in its **own separate view**. Resources from different PBS servers or clusters are not combined simply because they have the same visible names. PVE views can also reflect their explicit CLUSTER association.

Only dashboard types backed by real resources are offered. The dashboard is optional and the integration works normally without installing it.

<details>
<summary><b>📦 Dashboard requirements & installation</b></summary>

### Requirements

- Proxmox Extended Sensors
- [Card Mod](https://github.com/thomasloven/lovelace-card-mod)

### Installation

1. Install **Card Mod** from HACS if it is not already installed.
2. Add the following Lovelace resource as a **JavaScript Module**:

   ```text
   /proxmox_sensors/proxmox-dashboard.js
   ```

3. Reload the browser.
4. Create a new dashboard from **Settings → Dashboards → Add dashboard → Community**.
5. Select **Proxmox Extended Sensors**.
6. Choose one of the dashboard types offered for your installation: **PVE**, **PBS**, **CLUSTER** or **PDM**.

The generated dashboard remains strategy-driven until you choose **Take Control**.

</details>

<details>
<summary><b>🛠️ What happens when I use Take Control?</b></summary>

Home Assistant converts the generated dashboard into a normal editable Lovelace configuration. You can then reorganize the layout, remove cards, add your own entities and combine Proxmox information with anything else in Home Assistant.

The integration does not overwrite a dashboard that you have taken control of.

</details>

## 📸 Dashboard screenshots

<details>
<summary><b>PVE</b></summary>

<br>
<img src="img/Dashb_Node.png" alt="PVE dashboard" width="100%">

</details>

<details>
<summary><b>PBS</b></summary>

<br>
<img src="img/Dashb_PBS.png" alt="PBS dashboard" width="100%">

</details>

<details>
<summary><b>CLUSTER</b></summary>

<br>
<img src="img/Dashb_Cluster.png" alt="CLUSTER dashboard" width="100%">

</details>

<details>
<summary><b>PDM</b></summary>

<br>
<img src="img/Dashb_PDM.png" alt="PDM dashboard" width="100%">

</details>

---

## 🔄 Migration-Safe VM & LXC Monitoring

For PVE nodes correctly associated with the same configured cluster scope, VM/LXC identity is independent of the physical node currently hosting the guest.

When a guest migrates between those nodes, the integration reconciles it at its new location while keeping the same logical Home Assistant identity. This is designed to preserve the entities referenced by history, dashboards, automations and areas instead of creating a replacement guest simply because its Proxmox node changed.

Guest controls follow the reconciled VM/LXC to its current node.

> Migration reconciliation is progressive. Immediately after a move, the source device can remain temporarily empty while sensors and cleanup converge over subsequent coordinator cycles.

---

## 🛡️ Resilient Monitoring & Fault Isolation

The integration isolates API work so one failing subsystem does not unnecessarily invalidate the rest of the installation.

- Independent API task timeouts.
- Controlled concurrency to avoid API saturation.
- Preservation of last valid data for affected sections.
- Automatic recovery when communication returns.
- Safer cleanup during partial refreshes.
- PBS inventory preservation during temporary connection failures.
- Storage reconciliation only removes resources when current data confirms they have disappeared.

---

## 🔁 PVE Replication Status

Native monitoring for Proxmox VE replication jobs includes:

- **Replication Jobs** — number and inventory of configured replication jobs.
- **Replication Status** — global replication state and failed-job details.
- Duration, last/next replication, source and target, guest type, failure count and runtime freshness.

Replication identity is based on the Proxmox replication job rather than only the physical node, allowing replication information to remain associated with a migrated guest.

---

## 🌐 Proxmox Datacenter Manager (PDM)

Starting with **V5.2.0**, Proxmox Extended Sensors supports **Proxmox Datacenter Manager** as a fourth connection type alongside PVE, PBS and CLUSTER.

PDM provides a centralized view of connected Proxmox VE and Proxmox Backup Server environments through a single PDM connection.

### Available sensors

| Sensor | Description |
|---|---|
| **Status** | Overall PDM health and remote status. |
| **Inventory** | Managed PVE/PBS nodes, VMs, containers and storage inventory. |
| **Capacity** | Aggregated CPU, memory and storage usage. |
| **Updates** | Available updates across monitored remotes. |
| **Remote Status** | Status and subscription information for each configured remote. |
| **Remote Overview** | Resource inventory and capacity for each remote. |

A dedicated **PDM Dashboard** provides an overview of infrastructure health, inventory, capacity, updates and configured remotes.

PDM focuses on **centralized monitoring**. For detailed node hardware metrics, individual VM/LXC monitoring and management actions, configure the corresponding PVE, PBS or CLUSTER connections.

---

## 🗄️ Proxmox Backup Server (PBS)

PBS monitoring includes datastore usage, backups, deduplication and maintenance information.

### Maintenance actions

- **Garbage Collection (GC)** — direct datastore action.
- **Prune** — runs the configured Prune Job for the datastore.
- **Verify** — runs the configured Verify Job.
- **Sync** — runs the configured Sync Job when available.

Actions launched from Home Assistant are tracked using the exact **UPID** returned by PBS, allowing their real progression to be represented as:

**Started → Running → OK / Error**

When no Home Assistant-triggered UPID is available, the integration can fall back to the most recent matching PBS job for operations launched directly from PBS or by schedule.

Backup Job, Backup Age and Backup Health information is handled conservatively: when fresh task information is unavailable, stale restored data is not presented as current healthy state.

---

## ☁️ Remote / Hosted PBS

Proxmox Extended Sensors connects to PBS through the standard HTTPS API, so the PBS server does not need to be on the same local network as Home Assistant.

This has been successfully tested with a **hosted Proxmox Backup Server from Tuxis**, including datastore monitoring and authorized maintenance operations. Available information and actions depend on the permissions exposed by the hosting provider. Server-level hardware information may not be available on a hosted service.

### API token examples

A typical self-hosted PBS configuration can use a short token name:

```text
User:     homeassistant@realm
Token ID: home
Token:    <API token secret>
```

A hosted provider may require the complete token identifier. For example, Tuxis uses a format such as:

```text
Host:     https://pbs005.tuxis.nl
User:     FL000XX_USUARIO@pbs
Token ID: FL000XX@pbs!home
Token:    <API token secret>
```

If **Token ID** already contains `!`, the integration uses it as the complete API token identifier. If a short Token ID is supplied, the integration builds the identifier from `User!Token ID`.

> Never publish or share the API token secret.

---

## 🧩 Multi-PBS Support

Multiple PBS connections can be configured in Home Assistant. Each PBS entry receives a persistent server identity so server, datastore and maintenance information remains associated with the correct PBS instance.

PBS instances remain isolated even when different servers use **datastores with the same name**. Re-added PBS instances can recover their previous server identity, and historical server IDs are not immediately reused for unrelated servers.

The dashboard follows the same separation and gives each configured PBS instance its own view instead of mixing resources from different servers.

---

## ❤️ Sidecar Status

Each PVE node exposes a single **Sidecar Status** diagnostic sensor summarizing the health of:

- Memory
- Mounts
- Sensors
- SMART

Possible states are `ok`, `degraded`, `error` and `unknown`.

When a sidecar endpoint fails, previously valid hardware values can be preserved instead of disappearing immediately.

---

## 🌐 Cluster Monitoring

Monitor the Proxmox cluster as a whole with dedicated entities for:

- Nodes online
- Quorum and configured Corosync QDevice status
- CPU and RAM usage
- Running VMs and CTs
- Storage usage
- Firewall state
- Failed tasks
- Backup jobs, backup age and backup health
- Replication jobs and replication status

---

## 💽 Mounted Disks & Network Storage

Deep visibility into each node's storage layer:

- Automatic discovery of local and network mounts.
- CIFS/SMB and NFS information.
- Usage and mount details.
- Detection of missing mounts.
- Filtering of irrelevant temporary/system mounts.

---

## 🧠 Hardware & Node Monitoring

Hardware information is collected through Proxmox and the optional sidecar/lm-sensors path where supported.

- CPU and system health information.
- CPU Package/Core thermal monitoring where available.
- CPU core temperatures exposed as attributes of the CPU temperature entity.
- Raspberry Pi / ARM CPU temperature through `cpu_thermal` when x86 Package/Core labels are not available.
- Temperature, voltage and fan channel classification from lm-sensors data.
- Chipset and NVMe temperatures.
- NVMe SMART and health information.
- DIMM/SMBIOS information where supported by the sidecar.
- I/O Wait and network traffic.
- KSM information.
- Node update information.

The sensor classifier distinguishes common hwmon channels such as `tempN_input`, `inN_input` and `fanN_input`, preventing CPU voltage channels such as Vcore from occupying the CPU temperature sensor when real CPU temperature data is available.

---

## ⚡ Physical Wake-on-LAN

Physical PVE nodes can be started from Home Assistant with the integration's **Wake** button when a valid MAC address is configured.

Wake-on-LAN is sent **directly by Proxmox Extended Sensors** as a UDP magic packet. It does not depend on Home Assistant's optional `wake_on_lan.send_magic_packet` action or on the PVE API being reachable at that moment.

Because the magic packet is generated locally by the integration, the **Wake button remains available while the PVE node is offline**. Actions that require the Proxmox API, such as Shutdown or Reboot, remain unavailable while the node cannot be reached.

The target hardware, firmware and network must support Wake-on-LAN and be configured to accept the magic packet. Virtualized PBS/PVE systems depend on the capabilities of their virtual network interface and host; a virtual NIC such as VirtIO should not be assumed to provide physical Wake-on-LAN behavior.

---

## 🖥️ Virtual Machines & Containers

VM and LXC monitoring includes guest state and resource information exposed by Proxmox and the integration, including:

- CT memory percentage
- CT disk percentage
- VM memory percentage
- Optional **Guest Agent Metrics** for VM root filesystem percentage via QEMU Guest Agent
- `onboot`, expected state and state/onboot matching information
- Cluster-aware migration continuity for correctly associated nodes

---

## 💾 Backup Services (VMs & CTs)

The integration provides backup orchestration directly from Home Assistant.

### 🟦 Single/Batch Backup (`create_vzdump_backup`)

- Supports local storage, NFS and PBS targets.
- Multiple guest IDs can be backed up in one operation.
- Native Proxmox backup execution preserves compatibility with PBS deduplication.

### 🟩 Massive Backup (`backup_all`)

- Back up all guests on a node.
- Configurable concurrency and delays.
- Suitable for scheduled Home Assistant automations.

---

## 🧩 Supported Versions

- Proxmox VE 7.x / 8.x / 9.x
- Proxmox Backup Server 3.x / 4.x
- Home Assistant 2026.5+

---

## 🧩 Installation

### 🔹 Via HACS (Recommended)

[![Open your Home Assistant instance and open this fork in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=darthrater78&repository=proxmox_sensors&category=integration)

This fork is installed as a **HACS custom repository**. It uses the same integration domain as the upstream project, so remove the upstream download first; the two cannot be installed side by side.

1. Open **HACS → ⋮ → Custom repositories**, add `https://github.com/darthrater78/proxmox_sensors` with type **Integration**.
2. Search for **Proxmox Extended Sensors** and open the entry from `darthrater78/proxmox_sensors`.
3. Click **Download**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration**.
6. Search for **Proxmox Extended Sensors** and configure your PVE, PBS, CLUSTER and/or PDM connection.

> The optional Proxmox Dashboard is installed separately. See [Dynamic Proxmox Dashboard](#-dynamic-proxmox-dashboard).

---

## 🔐 Security Architecture

How this fork is built, and later changed, with regard to security. Every security fix updates this section.

**Components and trust boundaries**

- **Integration (Home Assistant).** Talks to the Proxmox VE / PBS / PDM HTTPS APIs with the credentials you enter. Home Assistant stores config-entry credentials in its own `.storage` directory; protect that directory and your Home Assistant backups like any other secret store.
- **Sidecar (`pve-sensors-api.py`, optional).** A small service on each PVE node, port 9000, that exposes read-only hardware data (lm-sensors, SMART, memory modules, mounts, KSM). It runs as root because SMART and DMI reads need raw device access. Every endpoint is a fixed command with no client-controlled arguments, except `/smart-disk`, which accepts only an existing block device under `/dev`.

**Sidecar security**

- **HTTPS with a pinned certificate.** The installer generates a self-signed ECDSA P-256 certificate; Home Assistant pins its SHA-256 fingerprint (entered from the installer's output, not fetched over the network) and refuses to send anything to a different certificate. TLS 1.2 is the minimum.
- **Token.** Every request carries a 256-bit random bearer token, compared in constant time. The sidecar refuses to start with a token but no TLS, or with a token in a config file readable by anyone but root.
- **Allow-list, enforced twice.** Connections from addresses outside `ALLOWED_IPS` are dropped before the TLS handshake, and systemd's `IPAddressDeny=any` / `IPAddressAllow=` block them at the kernel too.
- **Resource limits.** At most 8 requests are served at once (extra connections are refused, not queued), and a client has 15 seconds to complete the handshake and send its request.
- **Sandbox.** The systemd unit sets `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `NoNewPrivileges`, kernel-module/log/cgroup protection, namespace and address-family restrictions; it keeps raw device access, which SMART needs.
- **Verified installs.** The installer installs only a sidecar matching the release's `SHA256SUMS`.
- **Legacy mode.** `--legacy-http` (plain HTTP, allow-list only) stays available for compatibility; Home Assistant flags such a sidecar with a repair warning.
- **Errors stay on the node.** A failing endpoint answers with a fixed message such as `dmidecode failed`; exception text and command output, which can name devices and serial numbers, go only to the node's journal (`journalctl -u pve-sensors`).
- **Sleeping disks stay asleep.** The SMART scan queries disks with `smartctl -n standby`, so a spun-down disk is reported as in standby, not woken; Home Assistant keeps that disk's last reading.

**Transport security (Proxmox APIs)**

- With **Verify SSL Certificate** on, certificates are checked against the system trust store (use this with ACME / Let's Encrypt certificates).
- With it off (Proxmox's own self-signed certificates), the server certificate's **SHA-256 fingerprint is pinned**. During setup the fingerprint is shown for you to compare with the Proxmox web interface (Node → System → Certificates), and your password or token is sent only after you confirm. Every later request, including the password login itself, is refused unless the server presents that exact certificate. TLS 1.2 is the minimum.
- Entries created before pinning existed pin the certificate they see on their next start and show a notification with the fingerprint to check.
- If the certificate changes, or the password/token stops working, Home Assistant opens a **reauthentication** prompt that shows the old and new fingerprints; nothing is sent to the server until you accept.

**Actions and services**

- Node reboot and shutdown are **opt-in** (`enable_node_controls`, off unless you turn it on), for both the buttons and the `confirm_shutdown_node` / `confirm_reboot_node` services.
- Every domain service that changes something (`create_vzdump_backup`, `backup_all`, `confirm_shutdown_node`, `confirm_reboot_node`, `wake_node`) requires a Home Assistant **administrator**, and validates its input (backup mode and compression from fixed lists, bounded concurrency and delays, strict MAC address format).

**Supply chain**

- Every GitHub Action is pinned to a commit SHA, except `hacs/action`: it is a Docker action that always runs HACS's moving `ghcr.io/hacs/action:main` image, so a commit pin would not fix the code that runs. Its CI job has read-only access, no secrets and no stored credentials; Dependabot keeps pins and Python dependencies current, and CodeQL, dependency review and a weekly `pip-audit` watch for vulnerabilities.
- Each release attaches the sidecar and its installer with a `SHA256SUMS` file and a signed build-provenance attestation. Check a download with `gh attestation verify pve-sensors-api.py --repo darthrater78/proxmox_sensors`.
- Releases are published only from tags on `main` whose commit passed CI and whose `manifest.json` version matches the tag.

**Known limits**

- The sidecar runs as root with raw device access; the sandbox narrows what it can touch, not the devices SMART needs.
- `SHA256SUMS` comes from the same release as the files it covers, so it catches corrupted or swapped downloads but not a compromised release; `gh attestation verify` checks that the files were built by this repository's release workflow.

---

## 🙌 Special Thanks

Special thanks to the community members who test the integration across different hardware and Proxmox environments and contribute bug reports, diagnostics, code and validation.

Thank you to everyone who reports issues, tests fixes and helps make the integration more reliable. ❤️

---

## 🤝 Contributing

Contributions, testing and bug reports are welcome.

Please use the GitHub issue tracker for reproducible problems and include relevant Home Assistant / Proxmox logs where appropriate.

---

## 📄 License

MIT License

Copyright (c) Javisen. Fork changes copyright (c) darthrater78, under the same license.
