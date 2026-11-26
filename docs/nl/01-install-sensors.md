# 🌡️ Stap 1: Hardwaresensoren en Sidecar

Deze handleiding bereidt een Proxmox VE-node voor op hardwaredata die niet via de standaard Proxmox-API beschikbaar is. V5 gebruikt de sidecar voor temperaturen, geheugen, mounts en SMART en voegt **Sidecar Status** toe.

## 1. Pakketten installeren
```bash
apt update && apt install lm-sensors smartmontools -y
```

## 2. Sensoren detecteren
```bash
sensors-detect
```
Volg de wizard en activeer passende modules. Als `/etc/modules` wordt aangeboden, zorg dat benodigde modules na reboot blijven laden.

## 3. Controleren
```bash
sensors
```
Voor Intel met `coretemp`, indien nodig:
```bash
modprobe coretemp
sensors
```
Forceer `coretemp` niet op systemen met een andere driver.

---

## 4. De Sidecar installeren

Voer de volgende opdracht als root uit op elke PVE-node waarop je de Hardware Sidecar wilt installeren:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

Tijdens de installatie word je gevraagd het IP-adres of de IP-adressen van je Home Assistant-instantie(s) in te voeren. Meerdere IP-adressen kun je scheiden met komma's. Alleen deze adressen kunnen de Sidecar bereiken.

Het installatiescript downloadt de Sidecar uit de nieuwste release van deze fork en installeert hem alleen als hij overeenkomt met het `SHA256SUMS`-bestand van die release. Daarna maakt het een zelfondertekend certificaat en een willekeurig token aan en toont beide:

- de **Sidecar token**
- de SHA-256-vingerafdruk van het certificaat (**Sidecar certificate SHA-256**)

Bewaar ze voor stap 6.

> **Let op:** Voer dezelfde opdracht opnieuw uit om een bestaande installatie bij te werken. Token en certificaat blijven behouden, dus Home Assistant blijft werken; `--rotate-token` of `--rotate-cert` vervangt ze.

## 5. De Sidecar controleren

Controleer de status van de Sidecar-service:

```bash
systemctl status pve-sensors.service
```

De service zou als `active (running)` moeten worden weergegeven. Zo niet, dan legt het logboek uit waarom:

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Home Assistant met de Sidecar verbinden

Zodra de PVE-vermelding van de node in Home Assistant bestaat (zie [03. Home Assistant instellen](03-login-pve-pbs.md)), open je **Instellingen → Apparaten & diensten → Proxmox Extended Sensors**, kies je de vermelding van de node en dan **⋮ → Opnieuw configureren**. Vul de **Sidecar token** en het **Sidecar certificate SHA-256** uit stap 4 in.

Home Assistant controleert ze bij de Sidecar voordat ze worden opgeslagen. Daarna stuurt het verzoeken alleen nog naar precies dat certificaat, met het token. Tot ze zijn ingevuld, blijven de hardwaresensoren van de node onbeschikbaar.

---

## 7. Bij storing
V5 bewaart waar mogelijk de laatste geldige hardwarewaarden. **Sidecar Status** toont Memory, Mounts, Sensors en SMART als `ok`, `degraded`, `error` of `unknown`.

Volgende: [02. Proxmox-gebruiker en rechten](02-proxmox-config.md)
