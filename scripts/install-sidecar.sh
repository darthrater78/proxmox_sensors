#!/usr/bin/env bash
# Proxmox Extended Sensors - hardware sidecar installer.
#
# Installs /usr/local/bin/pve-sensors-api.py as the pve-sensors systemd service.
# By default the sidecar serves HTTPS with a self-signed certificate and
# requires a random bearer token; both are printed at the end so you can enter
# them in Home Assistant (the PVE entry's Reconfigure page).
#
# The sidecar is downloaded from this fork's GitHub release and checked against
# that release's SHA256SUMS before it is installed.
#
# Usage: install-sidecar.sh [options]
#   --version TAG       install from release TAG (default: the latest release)
#   --local DIR         install DIR/pve-sensors-api.py, checked against DIR/SHA256SUMS
#   --allowed-ips LIST  comma-separated Home Assistant IPs (skips the prompt)
#   --rotate-token      generate a new token even if one exists
#   --rotate-cert       generate a new certificate even if one exists
#   --legacy-http       compatibility mode: plain HTTP and IP allow-list only
#                       (for integration versions without sidecar token support)
set -euo pipefail

REPO="darthrater78/proxmox_sensors"
SIDECAR_PATH="/usr/local/bin/pve-sensors-api.py"
CONFIG_DIR="/etc/proxmox-sensors"
CONFIG_PATH="${CONFIG_DIR}/sidecar.conf"
CERT_PATH="${CONFIG_DIR}/sidecar.crt"
KEY_PATH="${CONFIG_DIR}/sidecar.key"
SERVICE_PATH="/etc/systemd/system/pve-sensors.service"
PORT=9000

VERSION=""
LOCAL_DIR=""
ALLOWED_INPUT=""
ROTATE_TOKEN=0
ROTATE_CERT=0
LEGACY=0

die() { echo "Error: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="${2:?--version needs a tag}"; shift 2 ;;
    --local) LOCAL_DIR="${2:?--local needs a directory}"; shift 2 ;;
    --allowed-ips) ALLOWED_INPUT="${2:?--allowed-ips needs a list}"; shift 2 ;;
    --rotate-token) ROTATE_TOKEN=1; shift ;;
    --rotate-cert) ROTATE_CERT=1; shift ;;
    --legacy-http) LEGACY=1; shift ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

[[ ${EUID} -ne 0 ]] && die "this installer must be run as root."
for tool in python3 sha256sum systemctl; do
  command -v "${tool}" >/dev/null || die "${tool} is required."
done
[[ ${LEGACY} -eq 0 ]] && { command -v openssl >/dev/null || die "openssl is required."; }

echo "Proxmox Extended Sensors - Hardware Sidecar installer"
[[ -f "${SERVICE_PATH}" ]] && echo "Existing Sidecar installation detected."
echo

# Read a KEY's value from the existing config (parsed, never sourced).
config_value() {
  [[ -r "${CONFIG_PATH}" ]] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "${CONFIG_PATH}" \
    | tail -n1 | tr -d "\"' \r"
}

valid_ips() {
  python3 - "$1" <<'PY'
import ipaddress
import sys

items = [item.strip() for item in sys.argv[1].split(",") if item.strip()]
if not items:
    raise SystemExit(1)
for item in items:
    ipaddress.ip_address(item)
PY
}

# ----- allowed client addresses --------------------------------------------
if [[ -n "${ALLOWED_INPUT}" ]]; then
  valid_ips "${ALLOWED_INPUT}" 2>/dev/null || die "invalid --allowed-ips list."
else
  # The prompt needs a terminal; with `curl ... | bash` stdin is the script.
  [[ -t 0 ]] || die "stdin is not a terminal. Download the installer and run it, or pass --allowed-ips."
  DEFAULT_IPS="$(config_value ALLOWED_IPS)"
  echo "Enter the Home Assistant IP address(es) allowed to access the Sidecar."
  echo "Use commas to separate multiple addresses. Example: 192.168.1.50,192.168.1.60"
  [[ -n "${DEFAULT_IPS}" ]] && echo "Current value: ${DEFAULT_IPS} (press Enter to keep it)"
  while true; do
    read -r -e -i "${DEFAULT_IPS}" -p "Allowed IP(s): " ALLOWED_INPUT
    ALLOWED_INPUT="${ALLOWED_INPUT:-${DEFAULT_IPS}}"
    valid_ips "${ALLOWED_INPUT}" 2>/dev/null && break
    echo "Invalid IP list. Please try again."
  done
fi
ALLOWED_INPUT="${ALLOWED_INPUT// /}"

# ----- fetch and verify the sidecar ----------------------------------------
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

if [[ -n "${LOCAL_DIR}" ]]; then
  cp "${LOCAL_DIR}/pve-sensors-api.py" "${LOCAL_DIR}/SHA256SUMS" "${WORK}/" \
    || die "${LOCAL_DIR} must contain pve-sensors-api.py and SHA256SUMS."
else
  command -v curl >/dev/null || die "curl is required."
  if [[ -n "${VERSION}" ]]; then
    BASE="https://github.com/${REPO}/releases/download/${VERSION}"
  else
    BASE="https://github.com/${REPO}/releases/latest/download"
  fi
  echo "Downloading Sidecar from ${BASE} ..."
  for asset in pve-sensors-api.py SHA256SUMS; do
    curl -fsSL --proto '=https' --tlsv1.2 "${BASE}/${asset}" -o "${WORK}/${asset}" \
      || die "download of ${asset} failed."
  done
fi

( cd "${WORK}" && grep -E '^[0-9a-f]{64}  pve-sensors-api\.py$' SHA256SUMS | sha256sum -c --status - ) \
  || die "pve-sensors-api.py does not match SHA256SUMS; nothing was installed."
echo "Checksum verified."

# ----- token and certificate -----------------------------------------------
install -d -m 0750 "${CONFIG_DIR}"
TOKEN=""
if [[ ${LEGACY} -eq 0 ]]; then
  TOKEN="$(config_value TOKEN)"
  if [[ ${ROTATE_TOKEN} -eq 1 || ${#TOKEN} -lt 32 ]]; then
    TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    TOKEN_NEW=1
  fi
  if [[ ${ROTATE_CERT} -eq 1 || ! -s "${CERT_PATH}" || ! -s "${KEY_PATH}" ]]; then
    ( umask 077
      openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
        -days 3650 -subj "/CN=$(hostname -f 2>/dev/null || hostname) pve-sensors" \
        -keyout "${KEY_PATH}" -out "${CERT_PATH}" 2>/dev/null ) \
      || die "certificate generation failed."
    CERT_NEW=1
  fi
  chmod 0600 "${KEY_PATH}"
  chmod 0644 "${CERT_PATH}"
fi

( umask 077
  {
    echo "# Written by install-sidecar.sh - re-run it to change these settings."
    echo "ALLOWED_IPS=${ALLOWED_INPUT}"
    echo "PORT=${PORT}"
    if [[ ${LEGACY} -eq 0 ]]; then
      echo "TOKEN=${TOKEN}"
      echo "TLS_CERT=${CERT_PATH}"
      echo "TLS_KEY=${KEY_PATH}"
    fi
  } > "${CONFIG_PATH}.new" )
mv "${CONFIG_PATH}.new" "${CONFIG_PATH}"

install -m 0755 "${WORK}/pve-sensors-api.py" "${SIDECAR_PATH}"

# ----- systemd unit ---------------------------------------------------------
# Root is required for raw SMART/DMI access; everything else is fenced off.
IP_ALLOW="localhost ${ALLOWED_INPUT//,/ }"
cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=PVE Sensors API (Proxmox Extended Sensors sidecar)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -I ${SIDECAR_PATH}
Restart=always
RestartSec=10s
RuntimeDirectory=pve-sensors
WorkingDirectory=/run/pve-sensors

# Only the allowed Home Assistant addresses can reach the service at all.
IPAddressDeny=any
IPAddressAllow=${IP_ALLOW}
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectHostname=yes
ProtectClock=yes
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
SystemCallArchitectures=native
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pve-sensors.service >/dev/null
systemctl restart pve-sensors.service

sleep 1
if ! systemctl is-active --quiet pve-sensors.service; then
  echo
  echo "Sidecar failed to start."
  systemctl --no-pager -l status pve-sensors.service || true
  exit 1
fi

echo
echo "Sidecar installed/updated successfully."
echo "Allowed IP(s): ${ALLOWED_INPUT}"
if [[ ${LEGACY} -eq 1 ]]; then
  echo "Mode: COMPATIBILITY - plain HTTP on port ${PORT}, IP allow-list only."
  echo "Home Assistant will show a repair warning until you re-run this"
  echo "installer without --legacy-http and enter the token and fingerprint."
else
  FINGERPRINT="$(openssl x509 -in "${CERT_PATH}" -noout -fingerprint -sha256 | cut -d= -f2)"
  echo "Mode: HTTPS on port ${PORT} with token."
  echo
  echo "In Home Assistant open this node's Proxmox entry, choose Reconfigure,"
  echo "and enter:"
  echo "  Sidecar token:              ${TOKEN}"
  echo "  Sidecar certificate SHA-256: ${FINGERPRINT}"
  [[ -n "${TOKEN_NEW:-}" ]] && echo "(new token - Home Assistant needs the value above)"
  [[ -n "${CERT_NEW:-}" ]] && echo "(new certificate - Home Assistant needs the fingerprint above)"
  echo
  echo "The token is stored in ${CONFIG_PATH} (readable by root only)."
fi
