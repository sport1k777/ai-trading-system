#!/usr/bin/env bash
# Deploy the local working tree to a non-git production copy on the VPS.
#
# Production layout (your server):
#   /opt/ai-trading-system-backup   ← real files (rsync target)
#   /opt/ai-trading-system          ← symlink → backup
#
# This script NEVER uses git on the server and NEVER overwrites:
#   .env  venv/  .cache/
#
# Default mode copies observability + infra only (no strategy engine changes):
#   signal_service, pipeline TRACE, diagnostics, SSL helpers, systemd wrapper
#
# Usage (from your Mac, inside the project):
#   export DEPLOY_SSH=root@YOUR_VPS_IP
#   export DEPLOY_KEY=$HOME/.ssh/id_ed25519    # optional
#   ./scripts/deploy/rsync_production.sh
#
# Options:
#   --yes              skip confirmation prompt
#   --dry-run          show rsync actions only
#   --with-strategy    also sync app/analysis/ (changes engine logic — avoid for TRACE phase)
#   --full-app         sync entire app/ tree (implies analysis; use with care)
#   --no-restart       copy files but do not restart systemd
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_SSH="${DEPLOY_SSH:-}"
DEPLOY_KEY="${DEPLOY_KEY:-}"
REMOTE_ROOT="${REMOTE_ROOT:-/opt/ai-trading-system-backup}"
SYMLINK_PATH="${SYMLINK_PATH:-/opt/ai-trading-system}"
SERVICE_NAME="${SERVICE_NAME:-ai-trading-signals}"

AUTO_YES=0
DRY_RUN=0
WITH_STRATEGY=0
FULL_APP=0
NO_RESTART=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) AUTO_YES=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --with-strategy) WITH_STRATEGY=1 ;;
    --full-app) FULL_APP=1; WITH_STRATEGY=1 ;;
    --no-restart) NO_RESTART=1 ;;
    -h|--help)
      sed -n '1,30p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ -z "$DEPLOY_KEY" && -f "$HOME/.ssh/id_ed25519" ]]; then
  DEPLOY_KEY="$HOME/.ssh/id_ed25519"
fi

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)
if [[ -n "$DEPLOY_KEY" ]]; then
  SSH_OPTS+=(-i "$DEPLOY_KEY")
fi

RSYNC_SSH="ssh ${SSH_OPTS[*]}"
if [[ -n "$DEPLOY_KEY" ]]; then
  RSYNC_SSH="ssh ${SSH_OPTS[*]} -i ${DEPLOY_KEY}"
fi

log() { printf '[deploy] %s\n' "$*"; }
die() { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

run() {
  log ">>> $*"
  "$@"
}

ssh_cmd() {
  ssh "${SSH_OPTS[@]}" "$DEPLOY_SSH" "$@"
}

rsync_file() {
  local src="$1"
  local dest="$2"
  local -a opts=(-avz)
  if (( DRY_RUN )); then
    opts+=(-n --itemize-changes)
  fi
  run rsync "${opts[@]}" -e "$RSYNC_SSH" "$src" "$DEPLOY_SSH:$dest"
}

rsync_dir() {
  local src="$1"
  local dest="$2"
  local -a opts=(-avz)
  if (( DRY_RUN )); then
    opts+=(-n --itemize-changes)
  fi
  run rsync "${opts[@]}" -e "$RSYNC_SSH" "$src" "$DEPLOY_SSH:$dest"
}

[[ -n "$DEPLOY_SSH" ]] || die "Set DEPLOY_SSH, e.g. export DEPLOY_SSH=root@13.140.161.100"

# Required package — abort early if the local tree is incomplete.
REQUIRED_PATHS=(
  "app/diagnostics/__init__.py"
  "app/diagnostics/pipeline_diagnostic.py"
  "app/analysis/__init__.py"
  "app/analysis/market_regime.py"
)
for req in "${REQUIRED_PATHS[@]}"; do
  [[ -f "$ROOT_DIR/$req" ]] || die "Missing required local file: $req (cannot deploy runtime)"
done

# Analysis modules required by diagnostics + pipeline (runtime deps, not optional).
ANALYSIS_RUNTIME_PATHS=(
  "app/analysis/__init__.py"
  "app/analysis/market_regime.py"
  "app/analysis/market_context.py"
  "app/analysis/poi_proximity.py"
  "app/analysis/signal_generator.py"
  "app/analysis/bos.py"
  "app/analysis/choch.py"
  "app/analysis/structure.py"
  "app/analysis/structure_persistence.py"
  "app/analysis/swing.py"
  "app/analysis/fvg.py"
  "app/analysis/order_block.py"
  "app/analysis/liquidity.py"
  "app/analysis/pro/"
  "app/analysis/pro_v2/"
)

# --- default file set: infra + TRACE + diagnostics (no strategy) ---
DEPLOY_PATHS=(
  "app/services/signal_service.py"
  "app/pipeline.py"
  "app/diagnostics/"
  "${ANALYSIS_RUNTIME_PATHS[@]}"
  "app/utils/ssl_ca.py"
  "app/utils/bybit_client.py"
  "app/utils/logging_config.py"
  "app/collectors/"
  "app/telegram/"
  "app/config.py"
  "app/risk/"
  "app/indicators/"
  "scripts/fix_vps_ssl.sh"
  "scripts/run_signal_service_prod.sh"
  "scripts/telegram_test.py"
  "scripts/run_signal_service.py"
  "scripts/audit_24h.py"
  "deploy/systemd/ai-trading-signals.service"
  "pyproject.toml"
)

if (( FULL_APP )); then
  DEPLOY_PATHS=("app/" "${DEPLOY_PATHS[@]}")
elif (( WITH_STRATEGY )); then
  DEPLOY_PATHS=("app/analysis/" "${DEPLOY_PATHS[@]}")
fi

echo "========================================"
echo " AI Trading System — Rsync Production"
echo "========================================"
echo "Local project : $ROOT_DIR"
echo "Remote SSH    : $DEPLOY_SSH"
echo "Remote root   : $REMOTE_ROOT"
echo "Symlink path  : $SYMLINK_PATH"
echo "Strategy sync : $(( WITH_STRATEGY || FULL_APP ))"
echo "Dry run       : $DRY_RUN"
echo "========================================"

log "Testing SSH..."
ssh_cmd 'echo connected && uname -a' || die "SSH failed — fix auth before deploying"

log "Verifying remote layout..."
REMOTE_CHECK="$(ssh_cmd "set -e
if [[ ! -d '$REMOTE_ROOT' ]]; then echo MISSING_ROOT; exit 0; fi
if [[ -L '$SYMLINK_PATH' ]]; then
  target=\$(readlink -f '$SYMLINK_PATH')
  echo SYMLINK_OK target=\$target
else
  echo SYMLINK_WARN not_a_symlink
fi
if [[ -f '$REMOTE_ROOT/.env' ]]; then echo ENV_OK; else echo ENV_MISSING; fi
if [[ -x '$REMOTE_ROOT/venv/bin/python' ]]; then echo VENV_OK; else echo VENV_MISSING; fi
")"
echo "$REMOTE_CHECK"

echo "$REMOTE_CHECK" | grep -q "MISSING_ROOT" && die "Remote root missing: $REMOTE_ROOT"
echo "$REMOTE_CHECK" | grep -q "SYMLINK_OK target=$REMOTE_ROOT" || \
  log "WARN: $SYMLINK_PATH is not a symlink to $REMOTE_ROOT — rsync still targets $REMOTE_ROOT"

echo ""
log "Files/directories to sync:"
for rel in "${DEPLOY_PATHS[@]}"; do
  if [[ -e "$ROOT_DIR/$rel" ]]; then
    printf '  - %s\n' "$rel"
  else
    printf '  - %s (MISSING LOCALLY — skipped)\n' "$rel"
  fi
done

if (( ! AUTO_YES )); then
  echo ""
  read -r -p "Proceed with rsync to $REMOTE_ROOT? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || die "Aborted by user"
fi

STAMP="$(date -u +%Y%m%d-%H%M%S)"
if (( ! DRY_RUN )); then
  log "Creating remote backup snapshot: app.bak.$STAMP"
  ssh_cmd "mkdir -p '$REMOTE_ROOT/.deploy/backups' && \
    if [[ -d '$REMOTE_ROOT/app' ]]; then \
      cp -a '$REMOTE_ROOT/app' '$REMOTE_ROOT/.deploy/backups/app.$STAMP'; \
    fi"
fi

log "Syncing selected paths..."
for rel in "${DEPLOY_PATHS[@]}"; do
  local_path="$ROOT_DIR/$rel"
  [[ -e "$local_path" ]] || {
    log "WARN: missing locally, skipped: $rel"
    continue
  }

  if [[ -d "$local_path" ]]; then
    # Preserve directory name on the remote (app/diagnostics/, not flattened into app/).
    remote_dir="${REMOTE_ROOT}/${rel%/}"
    ssh_cmd "mkdir -p '$remote_dir'"
    rsync_dir "$local_path" "$remote_dir/"
  else
    remote_file="$REMOTE_ROOT/$rel"
    ssh_cmd "mkdir -p '$(dirname "$remote_file")'"
    rsync_file "$local_path" "$remote_file"
  fi
done

if (( DRY_RUN )); then
  log "Dry run complete — no remote changes made"
  exit 0
fi

log "Installing Python dependencies (preserves existing venv)"
ssh_cmd "cd '$REMOTE_ROOT' && \
  ./venv/bin/pip install --upgrade pip && \
  ./venv/bin/pip install -e ."

log "Verifying runtime imports on remote"
ssh_cmd "test -f '$REMOTE_ROOT/app/analysis/market_regime.py' && \
  test -f '$REMOTE_ROOT/app/diagnostics/__init__.py' && \
  cd '$REMOTE_ROOT' && PYTHONPATH=. ./venv/bin/python -c \"
from app.analysis.market_regime import MarketRegime, detect_market_regime, detect_regime_from_context
from app.diagnostics.pipeline_diagnostic import diagnose_scan_block
print('runtime_imports_ok')
\"" || die "Remote runtime import verification failed"

log "Ensuring production scripts are executable"
ssh_cmd "chmod +x \
  '$REMOTE_ROOT/scripts/fix_vps_ssl.sh' \
  '$REMOTE_ROOT/scripts/run_signal_service_prod.sh' \
  '$REMOTE_ROOT/scripts/run_signal_service.py' 2>/dev/null || true"

log "Installing systemd unit (ExecStart uses run_signal_service_prod.sh)"
rsync_file "$ROOT_DIR/deploy/systemd/ai-trading-signals.service" \
  "/etc/systemd/system/${SERVICE_NAME}.service"
ssh_cmd "systemctl daemon-reload"

if (( ! NO_RESTART )); then
  log "Restarting $SERVICE_NAME"
  ssh_cmd "systemctl restart '$SERVICE_NAME' && sleep 5 && systemctl is-active '$SERVICE_NAME'"
fi

echo ""
echo "========================================"
echo " DEPLOY COMPLETE"
echo "========================================"
echo "Verify symlink : ssh $DEPLOY_SSH 'readlink -f $SYMLINK_PATH'"
echo "Watch TRACE logs:"
echo "  ssh $DEPLOY_SSH 'journalctl -u $SERVICE_NAME -f | grep -E \"TRACE |Scan decision|Unhandled|Fetching candles\"'"
echo "Rollback app tree:"
echo "  ssh $DEPLOY_SSH 'rm -rf $REMOTE_ROOT/app && cp -a $REMOTE_ROOT/.deploy/backups/app.$STAMP $REMOTE_ROOT/app && systemctl restart $SERVICE_NAME'"
echo "========================================"
