# 🌡️ 第 1 步：硬件传感器与 Sidecar

本指南用于准备 Proxmox VE 节点，以读取标准 Proxmox API 未提供的硬件数据。V5 使用 sidecar 获取温度、内存、mount 和 SMART 数据，并提供 **Sidecar Status**。

## 1. 安装软件包
```bash
apt update && apt install lm-sensors smartmontools -y
```

## 2. 检测传感器
```bash
sensors-detect
```
按照向导启用适合硬件的模块。如果提示写入 `/etc/modules`，请确保所需模块在重启后仍会加载。

## 3. 验证
```bash
sensors
```
Intel 系统使用 `coretemp` 时，如有需要：
```bash
modprobe coretemp
sensors
```
不要在使用其他驱动的系统上强制加载 `coretemp`。

## 4. 安装 Sidecar

在每个需要安装 Hardware Sidecar 的 PVE 节点上，以 root 身份运行以下命令：

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

安装过程中会提示输入 Home Assistant 实例的 IP 地址，多个地址用逗号分隔。只有这些地址可以访问 Sidecar。

安装程序会从本 fork 的最新 Release 下载 Sidecar，并且只有在其与该 Release 的 `SHA256SUMS` 一致时才会安装。随后它会生成自签名证书和随机令牌，并显示以下两项：

- 令牌（**Sidecar token**）
- 证书的 SHA-256 指纹（**Sidecar certificate SHA-256**）

请保存好，第 6 步会用到。

> **注意：** 再次运行同一命令即可更新现有安装。令牌和证书会保留，因此 Home Assistant 可继续工作；`--rotate-token` 或 `--rotate-cert` 会替换它们。

## 5. 检查 Sidecar

检查 Sidecar 服务的状态：

```bash
systemctl status pve-sensors.service
```

服务应显示为 `active (running)`。如果不是，可通过其日志查看原因：

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. 将 Home Assistant 连接到 Sidecar

在 Home Assistant 中创建该节点的 PVE 条目后（参见 [03. Home Assistant 设置](03-login-pve-pbs.md)），打开 **Settings → Devices & Services → Proxmox Extended Sensors**，选择该节点的条目，然后点击 **⋮ → Reconfigure**。填入第 4 步中的 **Sidecar token** 和 **Sidecar certificate SHA-256**。

Home Assistant 会在保存前向 Sidecar 验证这两项。此后它只会携带令牌向该证书发送请求。在填写之前，该节点的硬件传感器将不可用。

## 7. Sidecar 故障时
V5 会尽可能保留最后一次有效硬件值。**Sidecar Status** 将 Memory、Mounts、Sensors 和 SMART 显示为 `ok`、`degraded`、`error` 或 `unknown`。

下一步：[02. Proxmox 用户与权限](02-proxmox-config.md)
