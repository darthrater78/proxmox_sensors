# 🔌 Шаг 3: Home Assistant — PVE, PBS и CLUSTER

## 1. HACS
[![Открыть в HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=darthrater78&repository=proxmox_sensors&category=integration)

Этот форк устанавливается как пользовательский репозиторий HACS и использует тот же домен интеграции, что и исходный проект, поэтому сначала удалите исходную загрузку. В **HACS → ⋮ → Пользовательские репозитории** добавьте `https://github.com/darthrater78/proxmox_sensors` с типом **Интеграция**, найдите **Proxmox Extended Sensors**, скачайте и перезапустите Home Assistant.

## 2. Добавить интеграцию
**Настройки → Устройства и службы → Добавить интеграцию → Proxmox Extended Sensors**. Типы: **PVE**, **PBS**, **CLUSTER**.

## 3. Host и аутентификация
Введите IP или hostname. PVE поддерживает user/password или API Token; PBS в текущем V5 использует API Token. Для token укажите полный User с realm, только имя token как Token ID и Token Secret.

## 4. PVE
После подключения обнаруживаются узлы и ресурсы: VM, LXC, storages, hardware. Cluster-wide идентичность V5 позволяет сущностям VM/LXC следовать за миграциями.

## 5. PBS
Каждый PBS имеет отдельную config entry и постоянную идентичность. Доступны datastore, backup, дедупликация, tasks, GC, Prune, Verify и Sync при наличии Sync Job.

## 6. CLUSTER
Включает quorum, узлы, агрегированные CPU/RAM, количество VM/CT, cluster storage, failed tasks, backup health и PVE replication.

## 7. Необязательный dashboard
Установите Card Mod, добавьте `/proxmox_sensors/proxmox-dashboard.js` как JavaScript Module, перезагрузите браузер и создайте dashboard со стратегией **Proxmox Extended Sensors**. Выберите PVE/PBS/CLUSTER. **Take Control** позволяет обычное редактирование Lovelace.

## 8. Managed PBS
Провайдер может ограничивать аппаратные и низкоуровневые данные. Доступные сущности зависят от API-доступа и прав.

Далее: [04. FAQ](04-faq.md)
