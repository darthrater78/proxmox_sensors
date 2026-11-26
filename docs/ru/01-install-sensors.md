# 🌡️ Шаг 1: Аппаратные датчики и Sidecar

Руководство подготавливает узел Proxmox VE к чтению аппаратных данных, которых нет в стандартном API Proxmox. V5 использует sidecar для температур, памяти, mounts и SMART и добавляет **Sidecar Status**.

## 1. Установить пакеты
```bash
apt update && apt install lm-sensors smartmontools -y
```

## 2. Обнаружить датчики
```bash
sensors-detect
```
Следуйте мастеру и включите подходящие модули. Если предлагается запись в `/etc/modules`, сохраните необходимые модули для загрузки после перезапуска.

## 3. Проверить
```bash
sensors
```
Для Intel с `coretemp`, если требуется:
```bash
modprobe coretemp
sensors
```
Не используйте `coretemp` принудительно на системах с другим драйвером.

## 4. Установка Sidecar

Выполните следующую команду от root на каждом узле PVE, где нужен Hardware Sidecar:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

Во время установки потребуется ввести IP-адрес(а) ваших экземпляров Home Assistant. Несколько адресов можно указать через запятую. Только эти адреса смогут подключаться к Sidecar.

Установщик загружает Sidecar из последнего релиза этого форка и устанавливает его, только если файл совпадает с `SHA256SUMS` релиза. Затем он создаёт самоподписанный сертификат и случайный токен и выводит оба значения:

- токен (**Sidecar token**)
- отпечаток SHA-256 сертификата (**Sidecar certificate SHA-256**)

Сохраните их для шага 6.

> **Примечание:** Чтобы обновить существующую установку, выполните ту же команду ещё раз. Токен и сертификат сохраняются, поэтому Home Assistant продолжает работать; `--rotate-token` или `--rotate-cert` заменяют их.

## 5. Проверка Sidecar

Проверьте состояние службы Sidecar:

```bash
systemctl status pve-sensors.service
```

Служба должна отображаться как `active (running)`. Если это не так, причина видна в её журнале:

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Подключение Home Assistant к Sidecar

Когда запись PVE для узла уже создана в Home Assistant (см. [03. Настройка Home Assistant](03-login-pve-pbs.md)), откройте **Настройки → Устройства и службы → Proxmox Extended Sensors**, выберите запись узла и затем **⋮ → Перенастроить**. Введите **Sidecar token** и **Sidecar certificate SHA-256** из шага 4.

Home Assistant проверяет их на Sidecar перед сохранением. После этого он отправляет запросы только на этот сертификат и вместе с токеном. Пока они не введены, аппаратные датчики узла недоступны.

## 7. При сбое
V5 по возможности сохраняет последние корректные аппаратные значения. **Sidecar Status** показывает Memory, Mounts, Sensors и SMART как `ok`, `degraded`, `error` или `unknown`.

Далее: [02. Пользователь и права Proxmox](02-proxmox-config.md)
