# 🌡️ Крок 1: Апаратні датчики та Sidecar

Посібник готує вузол Proxmox VE до апаратних даних, яких немає у стандартному API Proxmox. V5 використовує sidecar для температур, пам'яті, mounts і SMART та додає **Sidecar Status**.

## 1. Встановити пакети
```bash
apt update && apt install lm-sensors smartmontools -y
```

## 2. Виявити датчики
```bash
sensors-detect
```
Дотримуйтесь майстра та активуйте відповідні модулі. Якщо пропонується запис до `/etc/modules`, збережіть необхідні модулі для завантаження після перезапуску.

## 3. Перевірити
```bash
sensors
```
Для Intel із `coretemp`, якщо потрібно:
```bash
modprobe coretemp
sensors
```
Не використовуйте `coretemp` примусово на системах з іншим драйвером.

---

## 4. Встановлення Sidecar

Виконайте таку команду від root на кожному вузлі PVE, де потрібен Hardware Sidecar:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

Під час встановлення потрібно ввести IP-адресу(и) ваших екземплярів Home Assistant. Кілька адрес можна вказати через кому. Лише ці адреси зможуть підключатися до Sidecar.

Інсталятор завантажує Sidecar з останнього релізу цього форку й встановлює його, лише якщо файл збігається з `SHA256SUMS` релізу. Потім він створює самопідписаний сертифікат і випадковий токен та виводить обидва значення:

- токен (**Sidecar token**)
- відбиток SHA-256 сертифіката (**Sidecar certificate SHA-256**)

Збережіть їх для кроку 6.

> **Примітка:** Щоб оновити наявне встановлення, виконайте ту саму команду ще раз. Токен і сертифікат зберігаються, тож Home Assistant продовжує працювати; `--rotate-token` або `--rotate-cert` замінюють їх.

## 5. Перевірка Sidecar

Перевірте стан служби Sidecar:

```bash
systemctl status pve-sensors.service
```

Служба повинна відображатися як `active (running)`. Якщо ні, причину видно в її журналі:

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Підключення Home Assistant до Sidecar

Коли запис PVE для вузла вже створено в Home Assistant (див. [03. Налаштування Home Assistant](03-login-pve-pbs.md)), відкрийте **Налаштування → Пристрої та служби → Proxmox Extended Sensors**, виберіть запис вузла, а потім **⋮ → Переналаштувати**. Введіть **Sidecar token** і **Sidecar certificate SHA-256** з кроку 4.

Home Assistant перевіряє їх на Sidecar перед збереженням. Після цього він надсилає запити лише на цей сертифікат і разом із токеном. Доки їх не введено, апаратні датчики вузла недоступні.

---

## 7. При збої
V5 за можливості зберігає останні коректні апаратні значення. **Sidecar Status** показує Memory, Mounts, Sensors і SMART як `ok`, `degraded`, `error` або `unknown`.

Далі: [02. Користувач і дозволи Proxmox](02-proxmox-config.md)
