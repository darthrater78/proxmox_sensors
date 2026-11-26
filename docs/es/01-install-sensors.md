# 🌡️ Paso 1: Configuración de sensores de hardware y Sidecar

Esta guía prepara un nodo Proxmox VE para que **Proxmox Extended Sensors V5** pueda leer información de hardware que no está disponible a través de la API estándar de Proxmox.

El sidecar de hardware se utiliza para obtener datos como temperaturas, información de memoria, discos montados y detalles SMART. V5 también expone una entidad de diagnóstico **Sidecar Status** para que Home Assistant pueda informar del estado de estos endpoints.

---

## 1. Instalar los paquetes necesarios

Instala las utilidades de hardware y SMART en el host Proxmox:

```bash
apt update && apt install lm-sensors smartmontools -y
```

- **lm-sensors** → CPU, placa base, chipset, VRM, ventiladores y otros sensores compatibles
- **smartmontools** → información SMART de HDD, SSD y dispositivos NVMe compatibles

---

## 2. Detectar los sensores de hardware

Ejecuta:

```bash
sensors-detect
```

Sigue el asistente y habilita los módulos adecuados para tu hardware.

> [!CAUTION]
> Al finalizar `sensors-detect`, lee atentamente la pregunta. Si te pide guardar los módulos detectados en `/etc/modules`, asegúrate de guardar los necesarios para que también se carguen después de reiniciar.

---

## 3. Verificar `lm-sensors`

Ejecuta:

```bash
sensors
```

Deberías ver los sensores expuestos por tu hardware y los controladores del kernel.

Si tu sistema Intel utiliza `coretemp` y no se ha cargado automáticamente, puedes probarlo con:

```bash
modprobe coretemp
sensors
```

No fuerces `coretemp` en sistemas que utilicen otro controlador de sensores de hardware.

---

## 4. Instalar el Sidecar

Ejecuta el siguiente comando como root en cada nodo PVE donde quieras instalar el Hardware Sidecar:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

Durante la instalación, se te pedirá que introduzcas la dirección o direcciones IP de tus instancias de Home Assistant. Puedes introducir varias direcciones IP separadas por comas. Solo esas direcciones podrán acceder al Sidecar.

El instalador descarga el Sidecar de la última versión publicada de este fork y solo lo instala si coincide con el archivo `SHA256SUMS` de esa versión. Después genera un certificado autofirmado y un token aleatorio, y muestra ambos:

- el **Sidecar token**
- la huella SHA-256 del certificado (**Sidecar certificate SHA-256**)

Guárdalos para el paso 6.

> **Nota:** Ejecuta de nuevo el mismo comando para actualizar una instalación existente. El token y el certificado se conservan, así que Home Assistant sigue funcionando; `--rotate-token` o `--rotate-cert` los sustituyen.

## 5. Comprobar el Sidecar

Comprueba el estado del servicio Sidecar:

```bash
systemctl status pve-sensors.service
```

El servicio debería aparecer como `active (running)`. Si no es así, su registro explica el motivo:

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Conectar Home Assistant con el Sidecar

Cuando la entrada PVE del nodo ya exista en Home Assistant (consulta [03. Configuración de Home Assistant](03-login-pve-pbs.md)), abre **Ajustes → Dispositivos y servicios → Proxmox Extended Sensors**, elige la entrada del nodo y después **⋮ → Reconfigurar**. Introduce el **Sidecar token** y el **Sidecar certificate SHA-256** del paso 4.

Home Assistant los comprueba contra el Sidecar antes de guardarlos. A partir de entonces solo envía peticiones a ese certificado exacto, junto con el token. Hasta que los introduzcas, los sensores de hardware del nodo no estarán disponibles.
---

## 7. Qué hace V5 si falla el sidecar

Un fallo temporal del sidecar no provoca que desaparezcan inmediatamente todas las entidades de hardware que anteriormente tenían datos válidos.

V5 conserva, cuando es posible, los últimos datos de hardware válidos y expone un sensor **Sidecar Status** por cada nodo PVE con el estado de:

- Memoria
- Montajes
- Sensores
- SMART

Los estados habituales de Sidecar Status son:

- `ok`
- `degraded`
- `error`
- `unknown`

---

## ✔ Conclusión

Cuando `lm-sensors`, el soporte SMART y `pve-sensors.service` estén funcionando, Home Assistant podrá obtener la información adicional de hardware compatible con tu host Proxmox.

Siguiente: [02. Usuario y permisos de Proxmox](02-proxmox-config.md)
