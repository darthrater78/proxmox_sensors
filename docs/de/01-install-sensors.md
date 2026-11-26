# 🌡️ Schritt 1: Hardware-Sensoren und Sidecar

Diese Anleitung bereitet einen Proxmox-VE-Knoten für Hardwaredaten vor, die nicht über die Standard-Proxmox-API verfügbar sind. V5 nutzt den Sidecar unter anderem für Temperaturen, Speicherinformationen, Mounts und SMART und stellt zusätzlich **Sidecar Status** bereit.

## 1. Pakete installieren
```bash
apt update && apt install lm-sensors smartmontools -y
```
`lm-sensors` liefert unterstützte CPU-, Mainboard-, Chipsatz-, VRM- und Lüfterdaten; `smartmontools` SMART-Daten für HDD, SSD und unterstützte NVMe-Geräte.

## 2. Sensoren erkennen
```bash
sensors-detect
```
Folge dem Assistenten und aktiviere die für deine Hardware passenden Module. Werden Einträge für `/etc/modules` angeboten, stelle sicher, dass die benötigten Module für Neustarts gespeichert werden.

## 3. Prüfen
```bash
sensors
```
Bei Intel-Systemen mit `coretemp` kann bei Bedarf getestet werden:
```bash
modprobe coretemp
sensors
```
`coretemp` nicht auf Systemen erzwingen, die einen anderen Treiber verwenden.

## 4. Sidecar installieren

Führe den folgenden Befehl als root auf jedem PVE-Node aus, auf dem du den Hardware-Sidecar installieren möchtest:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

Während der Installation wirst du aufgefordert, die IP-Adresse(n) deiner Home-Assistant-Instanz(en) einzugeben. Mehrere IP-Adressen können durch Kommas getrennt angegeben werden. Nur diese Adressen können den Sidecar erreichen.

Das Installationsskript lädt den Sidecar aus dem neuesten Release dieses Forks herunter und installiert ihn nur, wenn er mit der `SHA256SUMS`-Datei des Releases übereinstimmt. Anschließend erzeugt es ein selbstsigniertes Zertifikat und ein zufälliges Token und zeigt beides an:

- das **Sidecar token**
- den SHA-256-Fingerabdruck des Zertifikats (**Sidecar certificate SHA-256**)

Bewahre beides für Schritt 6 auf.

> **Hinweis:** Führe denselben Befehl erneut aus, um eine bestehende Installation zu aktualisieren. Token und Zertifikat bleiben erhalten, sodass Home Assistant weiter funktioniert; `--rotate-token` bzw. `--rotate-cert` ersetzt sie.

## 5. Sidecar prüfen

Überprüfe den Status des Sidecar-Dienstes:

```bash
systemctl status pve-sensors.service
```

Der Dienst sollte als `active (running)` angezeigt werden. Falls nicht, erklärt sein Log den Grund:

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Home Assistant mit dem Sidecar verbinden

Sobald der PVE-Eintrag des Nodes in Home Assistant existiert (siehe [03. Home-Assistant-Einrichtung](03-login-pve-pbs.md)), öffne **Einstellungen → Geräte & Dienste → Proxmox Extended Sensors**, wähle den Eintrag des Nodes und dann **⋮ → Neu konfigurieren**. Trage **Sidecar token** und **Sidecar certificate SHA-256** aus Schritt 4 ein.

Home Assistant prüft beides vor dem Speichern am Sidecar. Danach sendet es Anfragen nur noch an genau dieses Zertifikat, zusammen mit dem Token. Bis beides eingetragen ist, bleiben die Hardware-Sensoren des Nodes nicht verfügbar.

## 7. Verhalten bei Sidecar-Ausfall
V5 behält nach Möglichkeit die letzten gültigen Hardwarewerte. **Sidecar Status** zeigt pro PVE-Knoten den Zustand von Memory, Mounts, Sensors und SMART als `ok`, `degraded`, `error` oder `unknown`.

Weiter: [02. Proxmox-Benutzer und Berechtigungen](02-proxmox-config.md)
