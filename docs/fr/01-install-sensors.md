# 🌡️ Étape 1 : Capteurs matériels et Sidecar

Cette procédure prépare un nœud Proxmox VE pour les données matérielles non exposées par l'API Proxmox standard. V5 utilise le sidecar pour les températures, la mémoire, les montages et SMART, et expose **Sidecar Status**.

## 1. Installer les paquets
```bash
apt update && apt install lm-sensors smartmontools -y
```

## 2. Détecter les capteurs
```bash
sensors-detect
```
Suivez l'assistant et activez les modules adaptés au matériel. Si l'assistant propose d'ajouter les modules à `/etc/modules`, enregistrez ceux nécessaires au redémarrage.

## 3. Vérifier
```bash
sensors
```
Pour un système Intel utilisant `coretemp`, si nécessaire :
```bash
modprobe coretemp
sensors
```
Ne forcez pas `coretemp` sur un système utilisant un autre pilote.

## 4. Installer le Sidecar

Exécutez la commande suivante en tant que root sur chaque nœud PVE sur lequel vous souhaitez installer le Hardware Sidecar :

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

Lors de l'installation, vous serez invité à saisir l'adresse ou les adresses IP de vos instances Home Assistant. Plusieurs adresses IP peuvent être saisies en les séparant par des virgules. Seules ces adresses peuvent joindre le Sidecar.

L'installateur télécharge le Sidecar depuis la dernière version publiée de ce fork et ne l'installe que s'il correspond au fichier `SHA256SUMS` de cette version. Il génère ensuite un certificat auto-signé et un jeton aléatoire, et affiche les deux :

- le jeton (**Sidecar token**)
- l'empreinte SHA-256 du certificat (**Sidecar certificate SHA-256**)

Conservez-les pour l'étape 6.

> **Remarque :** Exécutez à nouveau la même commande pour mettre à jour une installation existante. Le jeton et le certificat sont conservés, Home Assistant continue donc de fonctionner ; `--rotate-token` ou `--rotate-cert` les remplacent.

## 5. Vérifier le Sidecar

Vérifiez l'état du service Sidecar :

```bash
systemctl status pve-sensors.service
```

Le service devrait apparaître comme `active (running)`. Sinon, son journal en indique la raison :

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Connecter Home Assistant au Sidecar

Une fois l'entrée PVE du nœud créée dans Home Assistant (voir [03. Configuration de Home Assistant](03-login-pve-pbs.md)), ouvrez **Paramètres → Appareils et services → Proxmox Extended Sensors**, choisissez l'entrée du nœud, puis **⋮ → Reconfigurer**. Saisissez le **Sidecar token** et le **Sidecar certificate SHA-256** de l'étape 4.

Home Assistant les vérifie auprès du Sidecar avant de les enregistrer. Ensuite, il n'envoie ses requêtes qu'à ce certificat précis, avec le jeton. Tant qu'ils ne sont pas saisis, les capteurs matériels du nœud restent indisponibles.

---

## 7. En cas de panne
V5 conserve si possible les dernières valeurs matérielles valides. **Sidecar Status** indique l'état de Memory, Mounts, Sensors et SMART : `ok`, `degraded`, `error` ou `unknown`.

Suivant : [02. Utilisateur et permissions Proxmox](02-proxmox-config.md)
