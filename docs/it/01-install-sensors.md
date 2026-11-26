# 🌡️ Passo 1: Sensori hardware e Sidecar

Questa guida prepara un nodo Proxmox VE per i dati hardware non esposti dalla normale API Proxmox. V5 usa il sidecar per temperature, memoria, mount e SMART e aggiunge **Sidecar Status**.

## 1. Installa i pacchetti
```bash
apt update && apt install lm-sensors smartmontools -y
```

## 2. Rileva i sensori
```bash
sensors-detect
```
Segui la procedura e abilita i moduli adatti all'hardware. Se viene proposto di salvarli in `/etc/modules`, assicurati che quelli necessari siano persistenti dopo il riavvio.

## 3. Verifica
```bash
sensors
```
Su Intel con `coretemp`, se necessario:
```bash
modprobe coretemp
sensors
```
Non forzare `coretemp` su sistemi che usano un driver diverso.

## 4. Installare il Sidecar

Esegui il seguente comando come root su ogni nodo PVE in cui vuoi installare l'Hardware Sidecar:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

Durante l'installazione ti verrà chiesto di inserire l'indirizzo o gli indirizzi IP delle tue istanze di Home Assistant. Più indirizzi IP possono essere separati da virgole. Solo questi indirizzi possono raggiungere il Sidecar.

Il programma di installazione scarica il Sidecar dall'ultima release di questo fork e lo installa solo se corrisponde al file `SHA256SUMS` della release. Poi genera un certificato autofirmato e un token casuale, e li mostra entrambi:

- il **Sidecar token**
- l'impronta SHA-256 del certificato (**Sidecar certificate SHA-256**)

Conservali per il passo 6.

> **Nota:** Esegui di nuovo lo stesso comando per aggiornare un'installazione esistente. Token e certificato vengono mantenuti, quindi Home Assistant continua a funzionare; `--rotate-token` o `--rotate-cert` li sostituiscono.

## 5. Verificare il Sidecar

Controlla lo stato del servizio Sidecar:

```bash
systemctl status pve-sensors.service
```

Il servizio dovrebbe risultare `active (running)`. In caso contrario, il suo log ne spiega il motivo:

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Collegare Home Assistant al Sidecar

Quando la voce PVE del nodo esiste in Home Assistant (vedi [03. Configurazione di Home Assistant](03-login-pve-pbs.md)), apri **Impostazioni → Dispositivi e servizi → Proxmox Extended Sensors**, scegli la voce del nodo e poi **⋮ → Riconfigura**. Inserisci il **Sidecar token** e il **Sidecar certificate SHA-256** del passo 4.

Home Assistant li verifica sul Sidecar prima di salvarli. Da quel momento invia richieste solo a quel certificato esatto, insieme al token. Finché non li inserisci, i sensori hardware del nodo restano non disponibili.

## 7. Guasto del sidecar
V5 conserva quando possibile gli ultimi valori hardware validi. **Sidecar Status** mostra Memory, Mounts, Sensors e SMART come `ok`, `degraded`, `error` o `unknown`.

Avanti: [02. Utente e permessi Proxmox](02-proxmox-config.md)
