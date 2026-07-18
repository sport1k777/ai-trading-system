#!/usr/bin/env bash
# Repair broken certifi / CA bundle on the VPS and verify Bybit HTTPS.
#
# Run ON THE VPS as root:
#   bash /opt/ai-trading-system/scripts/fix_vps_ssl.sh
#
# Does not change strategy or thresholds.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${DEPLOY_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
VENV="${VENV_DIR:-${DEPLOY_ROOT}/venv}"
PYTHON="${VENV}/bin/python"
PIP="${VENV}/bin/pip"
ENV_FILE="${ENV_FILE:-${DEPLOY_ROOT}/.env}"
SERVICE_NAME="${SERVICE_NAME:-ai-trading-signals}"

log() { printf '[fix-vps-ssl] %s\n' "$*"; }
die() { printf '[fix-vps-ssl] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -d "$DEPLOY_ROOT" ]] || die "Deploy root not found: $DEPLOY_ROOT"
[[ -x "$PYTHON" ]] || die "Venv python not found: $PYTHON"

log "Python: $("$PYTHON" -V 2>&1)"
log "Venv: $VENV"

log "Step 1 — install OS CA certificates"
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates
  update-ca-certificates || true
fi
SYSTEM_CA="/etc/ssl/certs/ca-certificates.crt"
[[ -f "$SYSTEM_CA" ]] || SYSTEM_CA="/etc/pki/tls/certs/ca-bundle.crt"
[[ -f "$SYSTEM_CA" ]] || die "No system CA bundle found — install ca-certificates package"

log "Step 2 — remove invalid SSL_* entries from .env"
if [[ -f "$ENV_FILE" ]]; then
  tmp="$(mktemp)"
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      SSL_CERT_FILE=*|REQUESTS_CA_BUNDLE=*|CURL_CA_BUNDLE=*)
        path="${line#*=}"
        if [[ -z "$path" || ! -f "$path" ]]; then
          log "Removing invalid env line: $line"
          continue
        fi
        ;;
    esac
    printf '%s\n' "$line"
  done < "$ENV_FILE" > "$tmp"
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

log "Step 3 — repair certifi inside venv"
"$PIP" install --upgrade pip
"$PIP" uninstall -y certifi 2>/dev/null || true
"$PIP" install --no-cache-dir --force-reinstall 'certifi>=2024.0'

CERTIFI_WHERE="$("$PYTHON" -c 'import certifi; print(certifi.where())')"
log "certifi.where() => $CERTIFI_WHERE"

if [[ ! -f "$CERTIFI_WHERE" ]]; then
  log "WARN: certifi cacert.pem still missing after reinstall"
  log "Listing certifi package directory:"
  find "$VENV/lib" -path '*/certifi/*' -maxdepth 3 2>/dev/null | head -20 || true
  CERTIFI_DIR="$(dirname "$CERTIFI_WHERE")"
  mkdir -p "$CERTIFI_DIR"
  log "Restoring cacert.pem from system bundle -> $CERTIFI_WHERE"
  cp -a "$SYSTEM_CA" "$CERTIFI_WHERE"
fi

[[ -f "$CERTIFI_WHERE" ]] || die "certifi cacert.pem still missing: $CERTIFI_WHERE"
log "certifi cacert.pem OK ($(wc -c < "$CERTIFI_WHERE") bytes)"

log "Step 4 — verify resolve_ca_bundle() returns existing file"
RESOLVED="$("$PYTHON" -c "
import os
from pathlib import Path
os.chdir('$DEPLOY_ROOT')
import sys
sys.path.insert(0, '$DEPLOY_ROOT')
from app.utils.ssl_ca import resolve_ca_bundle
p = resolve_ca_bundle()
assert Path(p).is_file(), p
print(p)
")"
[[ -f "$RESOLVED" ]] || die "resolve_ca_bundle returned missing file: $RESOLVED"
log "resolve_ca_bundle => $RESOLVED"

log "Step 5 — verify Bybit HTTPS kline fetch"
cd "$DEPLOY_ROOT"
PYTHONPATH="$DEPLOY_ROOT" "$PYTHON" - <<'PY'
from app.utils.bybit_client import BybitClient

client = BybitClient()
df = client.get_klines(symbol="BTCUSDT", interval="15", limit=5)
print(f"VERIFY_BYBIT_OK rows={len(df)} last_close={df.iloc[-1]['close']}")
PY

log "Step 6 — update systemd + restart service"
chmod +x "${DEPLOY_ROOT}/scripts/run_signal_service_prod.sh"
unit="/etc/systemd/system/${SERVICE_NAME}.service"
if [[ -f "$unit" ]]; then
  if ! grep -q 'run_signal_service_prod.sh' "$unit"; then
    sed -i "s|ExecStart=.*|ExecStart=${DEPLOY_ROOT}/scripts/run_signal_service_prod.sh|" "$unit"
    systemctl daemon-reload
  fi
  systemctl restart "$SERVICE_NAME"
  sleep 8
  systemctl is-active --quiet "$SERVICE_NAME" || {
    journalctl -u "$SERVICE_NAME" -n 40 --no-pager
    die "Service not active after restart"
  }
else
  die "systemd unit missing: $unit"
fi

log "Step 7 — production log checks"
if journalctl -u "$SERVICE_NAME" -n 80 --no-pager | grep -qiE 'TLS CA certificate|SSL certificate problem|invalid path'; then
  journalctl -u "$SERVICE_NAME" -n 80 --no-pager
  die "SSL errors still present in service logs"
fi

journalctl -u "$SERVICE_NAME" -n 50 --no-pager
log "Candle lines:"
journalctl -u "$SERVICE_NAME" --no-pager | grep -E 'Using CA bundle|Fetching candles|Bybit kline OK' | tail -10 || true
log "Scan decisions:"
journalctl -u "$SERVICE_NAME" --no-pager | grep 'Scan decision' | tail -5 || true

log "SSL repair complete — verify candle fetch and scan lines above"
