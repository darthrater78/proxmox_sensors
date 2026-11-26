# 🌡️ Step 1: Hardware Sensors and Sidecar Setup

This guide prepares a Proxmox VE node so **Proxmox Extended Sensors V5** can read hardware information that is not exposed by the standard Proxmox API.

The hardware sidecar is used for data such as temperatures, memory information, mounted disks and SMART details. V5 also exposes a **Sidecar Status** diagnostic entity so Home Assistant can report whether these endpoints are healthy.

---

## 1. Install the required packages

Install the hardware and SMART utilities on the Proxmox host:

```bash
apt update && apt install lm-sensors smartmontools -y
```

- **lm-sensors** → CPU, motherboard, chipset, VRM, fan and other supported sensor data
- **smartmontools** → SMART information for HDD, SSD and supported NVMe devices

---

## 2. Detect hardware sensors

Run:

```bash
sensors-detect
```

Follow the wizard and enable the modules appropriate for your hardware.

> [!CAUTION]
> At the end of `sensors-detect`, read the prompt carefully. If it asks whether detected modules should be added to `/etc/modules`, make sure the required modules are saved so they also load after reboot.

---

## 3. Verify `lm-sensors`

Run:

```bash
sensors
```

You should see the sensors exposed by your hardware and kernel drivers.

If your Intel system uses `coretemp` and it has not loaded automatically, you can test it with:

```bash
modprobe coretemp
sensors
```

Do not force `coretemp` on systems that use a different hardware sensor driver.

---

## 4. Install the Sidecar

Run the following command as root on each PVE node where you want the Hardware Sidecar:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

During installation, you will be prompted to enter the IP address(es) of your Home Assistant instance(s). Multiple IP addresses can be entered separated by commas. Only these addresses can reach the Sidecar.

The installer downloads the Sidecar from this fork's latest release and installs it only if it matches the release's `SHA256SUMS`. It then generates a self-signed certificate and a random token, and prints both:

- the **Sidecar token**
- the **Sidecar certificate SHA-256** fingerprint

Keep them for step 6.

> **Note:** Run the same command again to update an existing installation. The token and certificate are kept, so Home Assistant keeps working; `--rotate-token` or `--rotate-cert` replaces them.

## 5. Check the Sidecar

Check the status of the Sidecar service:

```bash
systemctl status pve-sensors.service
```

The service should be shown as `active (running)`. If it is not, its log explains why:

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Connect Home Assistant to the Sidecar

Once the node's PVE entry exists in Home Assistant (see [03. Home Assistant Setup](03-login-pve-pbs.md)), open **Settings → Devices & Services → Proxmox Extended Sensors**, choose the node's entry, then **⋮ → Reconfigure**. Enter the **Sidecar token** and **Sidecar certificate SHA-256** from step 4.

Home Assistant checks them against the Sidecar before saving. From then on it sends requests only to that exact certificate, with the token. Until they are entered, the node's hardware sensors stay unavailable.

---

## 7. What V5 does when the sidecar fails

A temporary sidecar failure does not force all previously valid hardware entities to disappear immediately.

V5 preserves the last valid hardware data where possible and exposes one **Sidecar Status** sensor per PVE node with the state of:

- Memory
- Mounts
- Sensors
- SMART

Typical Sidecar Status states are:

- `ok`
- `degraded`
- `error`
- `unknown`

---

## ✔ Conclusion

Once `lm-sensors`, SMART support and `pve-sensors.service` are working, Home Assistant can obtain the additional hardware information supported by your Proxmox host.

Next: [02. Proxmox User and Permissions](02-proxmox-config.md)
