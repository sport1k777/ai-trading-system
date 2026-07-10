#!/usr/bin/env bash
# Production deployment for Contabo VPS (or any Linux host with systemd).
#
# PREFERRED: Git-based deployment on the VPS (preserves .env, venv, systemd):
#   See docs/GIT_DEPLOYMENT.md
#   ssh root@VPS 'bash /opt/ai-trading-system/scripts/deploy/deploy.sh'   # migrate once
#   ssh root@VPS 'bash /opt/ai-trading-system/scripts/deploy/update.sh'   # routine updates
#
# This rsync script remains as a legacy/bootstrap fallback from your laptop:
#   export DEPLOY_SSH="root@YOUR_VPS_IP"
#   export DEPLOY_KEY="$HOME/.ssh/id_ed25519"   # optional
#   ./scripts/deploy/contabo_deploy.sh
#
# The script prints every command before running it and stops on the first error.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REMOTE_DIR="${REMOTE_DIR:-/opt/ai-trading-system}"
SERVICE_NAME="${SERVICE_NAME:-ai-trading-signals}"
DEPLOY_SSH="${DEPLOY_SSH:-}"
DEPLOY_KEY="${DEPLOY_KEY:-}"

if [[ -z "$DEPLOY_KEY" && -f "$HOME/.ssh/id_ed25519" ]]; then
  DEPLOY_KEY="$HOME/.ssh/id_ed25519"
fi

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)
if [[ -n "${DEPLOY_KEY:-}" ]]; then
  SSH_OPTS+=(-i "$DEPLOY_KEY")
fi

run() {
  echo ""
  echo ">>> $*"
  "$@"
}

ssh_cmd() {
  run ssh "${SSH_OPTS[@]}" "$DEPLOY_SSH" "$@"
}

rsync_cmd() {
  local rsync_ssh="ssh ${SSH_OPTS[*]}"
  if [[ -n "${DEPLOY_KEY:-}" ]]; then
    rsync_ssh="ssh ${SSH_OPTS[*]} -i ${DEPLOY_KEY}"
  fi
  run rsync -az --delete \
    --exclude '.git/' \
    --exclude 'venv/' \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude '.DS_Store' \
    --exclude '.env' \
    -e "$rsync_ssh" \
    "$@"
}

fail() {
  echo ""
  echo "DEPLOYMENT FAILED: $1"
  echo ""
  echo "How to fix:"
  echo "$2"
  exit 1
}

if [[ -z "$DEPLOY_SSH" ]]; then
  fail "DEPLOY_SSH is not set." \
    "Export your VPS target, e.g.:\n  export DEPLOY_SSH=\"root@144.91.87.56\"\nIf your SSH key is not default, also set:\n  export DEPLOY_KEY=\"\$HOME/.ssh/your_private_key\""
fi

echo "========================================"
echo " AI Trading System — Production Deploy"
echo "========================================"
echo "Local project : $ROOT_DIR"
echo "Remote target : $DEPLOY_SSH"
echo "Remote path   : $REMOTE_DIR"
echo "Service name  : $SERVICE_NAME"
echo "========================================"

echo ""
echo ">>> ssh ${SSH_OPTS[*]} $DEPLOY_SSH 'echo connected && uname -a'"
if ! ssh "${SSH_OPTS[@]}" "$DEPLOY_SSH" 'echo connected && uname -a'; then
  fail "Cannot connect to $DEPLOY_SSH over SSH." \
    "1) Ensure the VPS is running and reachable.\n2) Load your SSH key: ssh-add ~/.ssh/your_key\n3) Test manually: ssh $DEPLOY_SSH\n4) If you see 'REMOTE HOST IDENTIFICATION HAS CHANGED', run:\n   ssh-keygen -R YOUR_VPS_IP\n5) Set DEPLOY_KEY if you use a non-default private key."
fi

echo ""
echo ">>> Installing system packages on VPS (python3, venv, rsync)..."
ssh_cmd "export DEBIAN_FRONTEND=noninteractive; \
  if command -v apt-get >/dev/null 2>&1; then \
    apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip rsync; \
  elif command -v dnf >/dev/null 2>&1; then \
    dnf install -y python3 python3-pip rsync; \
  elif command -v yum >/dev/null 2>&1; then \
    yum install -y python3 python3-pip rsync; \
  else \
    echo 'Unsupported package manager. Install python3, python3-venv, and rsync manually.' && exit 1; \
  fi"

echo ""
echo ">>> Creating remote directory $REMOTE_DIR"
ssh_cmd "mkdir -p '$REMOTE_DIR'"

echo ""
echo ">>> Rsync project files to VPS"
rsync_cmd "$ROOT_DIR/" "$DEPLOY_SSH:$REMOTE_DIR/"

echo ""
echo ">>> Uploading production .env"
ENV_TMP="$(mktemp)"
trap 'rm -f "$ENV_TMP"' EXIT

cat > "$ENV_TMP" <<EOF
BYBIT_API_KEY=
BYBIT_API_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ENABLED=true
TELEGRAM_NOTIFY_MIN_CONFIDENCE=90
SIGNAL_SERVICE_SCAN_INTERVAL_SECONDS=60
SIGNAL_SERVICE_SENT_STORE_PATH=.cache/telegram_sent_signals.json
SIGNAL_SERVICE_ERROR_BACKOFF_SECONDS=10
SIGNAL_SERVICE_RECONNECT_AFTER_ERRORS=3
TESTNET=false
DEFAULT_SYMBOL=BTCUSDT
DEFAULT_INTERVAL=15
DEFAULT_CANDLE_LIMIT=250
SCANNER_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT
LOG_LEVEL=INFO
AI_CONFIDENCE_THRESHOLD=90
EOF

if [[ -f "$ROOT_DIR/.env" ]]; then
  echo ">>> Merging values from local .env (Telegram / Bybit only)"
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    key="$(echo "$key" | xargs)"
    value="$(echo "$value" | xargs)"
    case "$key" in
      TELEGRAM_*|BYBIT_*|TESTNET|LOG_LEVEL|SCANNER_SYMBOLS|DEFAULT_*|SIGNAL_SERVICE_*|AI_CONFIDENCE_THRESHOLD)
        if grep -q "^${key}=" "$ENV_TMP"; then
          sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_TMP"
        else
          echo "${key}=${value}" >> "$ENV_TMP"
        fi
        ;;
    esac
  done < "$ROOT_DIR/.env"
  rm -f "${ENV_TMP}.bak"
fi

run scp "${SSH_OPTS[@]}" ${DEPLOY_KEY:+-i "$DEPLOY_KEY"} "$ENV_TMP" "$DEPLOY_SSH:$REMOTE_DIR/.env"
run ssh "${SSH_OPTS[@]}" ${DEPLOY_KEY:+-i "$DEPLOY_KEY"} "$DEPLOY_SSH" "chmod 600 '$REMOTE_DIR/.env'"

echo ""
echo ">>> Creating Python virtual environment and installing dependencies"
ssh_cmd "cd '$REMOTE_DIR' && \
  python3 -m venv venv && \
  ./venv/bin/pip install --upgrade pip && \
  ./venv/bin/pip install -e ."

echo ""
echo ">>> Installing systemd service"
run scp "${SSH_OPTS[@]}" ${DEPLOY_KEY:+-i "$DEPLOY_KEY"} \
  "$ROOT_DIR/deploy/systemd/ai-trading-signals.service" \
  "$DEPLOY_SSH:/etc/systemd/system/${SERVICE_NAME}.service"

echo ""
echo ">>> Enabling and starting systemd service"
ssh_cmd "systemctl daemon-reload && \
  systemctl enable ${SERVICE_NAME} && \
  systemctl restart ${SERVICE_NAME} && \
  sleep 3 && \
  systemctl is-active ${SERVICE_NAME}"

echo ""
echo ">>> Verifying Telegram integration"
ssh_cmd "cd '$REMOTE_DIR' && PYTHONPATH=. ./venv/bin/python scripts/telegram_test.py"

echo ""
echo ">>> Running one signal-service scan cycle"
ssh_cmd "cd '$REMOTE_DIR' && PYTHONPATH=. ./venv/bin/python - <<'PY'
from app.services.signal_service import SignalService
service = SignalService()
failures = service.run_cycle()
print(f'cycle_failures={failures}')
if failures:
    raise SystemExit(1)
PY"

echo ""
echo ">>> Service status"
ssh_cmd "systemctl status ${SERVICE_NAME} --no-pager -l | head -20"

echo ""
echo "========================================"
echo " DEPLOYMENT COMPLETE"
echo "========================================"
echo "Service : ${SERVICE_NAME}"
echo "Logs    : ssh $DEPLOY_SSH 'journalctl -u ${SERVICE_NAME} -f'"
echo "Status  : ssh $DEPLOY_SSH 'systemctl status ${SERVICE_NAME}'"
echo "Restart : ssh $DEPLOY_SSH 'systemctl restart ${SERVICE_NAME}'"
echo "========================================"
