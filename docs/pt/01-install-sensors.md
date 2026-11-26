# 🌡️ Passo 1: Sensores de hardware e Sidecar

Este guia prepara um nó Proxmox VE para dados de hardware que não são expostos pela API Proxmox padrão. V5 usa o sidecar para temperaturas, memória, mounts e SMART e adiciona **Sidecar Status**.

## 1. Instalar pacotes
```bash
apt update && apt install lm-sensors smartmontools -y
```

## 2. Detetar sensores
```bash
sensors-detect
```
Siga o assistente e ative os módulos adequados. Se for proposta a gravação em `/etc/modules`, assegure que os módulos necessários persistem após reiniciar.

## 3. Verificar
```bash
sensors
```
Em Intel com `coretemp`, se necessário:
```bash
modprobe coretemp
sensors
```
Não force `coretemp` em sistemas que usam outro driver.

---

## 4. Instalar o Sidecar

Execute o seguinte comando como root em cada nó PVE onde pretende instalar o Hardware Sidecar:

```bash
bash <(curl -fsSL https://github.com/darthrater78/proxmox_sensors/releases/latest/download/install-sidecar.sh)
```

Durante a instalação, ser-lhe-á pedido o endereço ou endereços IP das suas instâncias do Home Assistant. Pode introduzir vários endereços IP separados por vírgulas. Só estes endereços conseguem aceder ao Sidecar.

O instalador descarrega o Sidecar da versão mais recente deste fork e só o instala se corresponder ao ficheiro `SHA256SUMS` dessa versão. Depois gera um certificado autoassinado e um token aleatório, e mostra ambos:

- o **Sidecar token**
- a impressão digital SHA-256 do certificado (**Sidecar certificate SHA-256**)

Guarde-os para o passo 6.

> **Nota:** Execute novamente o mesmo comando para atualizar uma instalação existente. O token e o certificado são mantidos, pelo que o Home Assistant continua a funcionar; `--rotate-token` ou `--rotate-cert` substituem-nos.

## 5. Verificar o Sidecar

Verifique o estado do serviço Sidecar:

```bash
systemctl status pve-sensors.service
```

O serviço deverá aparecer como `active (running)`. Caso contrário, o respetivo registo explica porquê:

```bash
journalctl -u pve-sensors.service -n 50
```

## 6. Ligar o Home Assistant ao Sidecar

Quando a entrada PVE do nó já existir no Home Assistant (ver [03. Configuração do Home Assistant](03-login-pve-pbs.md)), abra **Definições → Dispositivos e serviços → Proxmox Extended Sensors**, escolha a entrada do nó e depois **⋮ → Reconfigurar**. Introduza o **Sidecar token** e o **Sidecar certificate SHA-256** do passo 4.

O Home Assistant verifica-os junto do Sidecar antes de os guardar. A partir daí envia pedidos apenas para esse certificado exato, com o token. Até serem introduzidos, os sensores de hardware do nó ficam indisponíveis.

---

## 7. Em caso de falha
V5 preserva, quando possível, os últimos valores de hardware válidos. **Sidecar Status** mostra Memory, Mounts, Sensors e SMART como `ok`, `degraded`, `error` ou `unknown`.

Seguinte: [02. Utilizador e permissões Proxmox](02-proxmox-config.md)
