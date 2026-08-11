#!/usr/bin/env bash
# Shared helpers for VPS Git deployment (deploy / update / rollback).
# Source this file — do not execute directly.

set -euo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/ai-trading-system}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/ai-trading-system-backups}"
SERVICE_NAME="${SERVICE_NAME:-ai-trading-signals}"
GIT_REPO="${GIT_REPO:-https://github.com/sport1k777/ai-trading-system.git}"
GIT_BRANCH="${GIT_BRANCH:-cursor/ai-signal-engine-production}"
VENV_DIR="${VENV_DIR:-${DEPLOY_ROOT}/venv}"
ENV_FILE="${ENV_FILE:-${DEPLOY_ROOT}/.env}"
DEPLOY_STATE_DIR="${DEPLOY_STATE_DIR:-${DEPLOY_ROOT}/.deploy}"
SYSTEMD_UNIT="${SYSTEMD_UNIT:-/etc/systemd/system/${SERVICE_NAME}.service}"
VERIFY_TIMEOUT_SECONDS="${VERIFY_TIMEOUT_SECONDS:-15}"

log()  { printf '[deploy] %s\n' "$*"; }
warn() { printf '[deploy] WARN: %s\n' "$*" >&2; }
die()  { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

run() {
  log ">>> $*"
  "$@"
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    die "Run as root on the VPS (e.g. sudo bash $0)"
  fi
}

require_commands() {
  local missing=()
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if ((${#missing[@]} > 0)); then
    die "Missing required commands: ${missing[*]}"
  fi
}

timestamp() {
  date -u +%Y%m%d-%H%M%S
}

ensure_dirs() {
  mkdir -p "$BACKUP_ROOT" "$DEPLOY_STATE_DIR" "${DEPLOY_STATE_DIR}/backups"
}

deployment_state() {
  # Prints: none | manual | git
  if [[ ! -d "$DEPLOY_ROOT" ]]; then
    echo "none"
    return 0
  fi
  if [[ -d "${DEPLOY_ROOT}/.git" ]]; then
    echo "git"
    return 0
  fi
  echo "manual"
}

is_git_repo() {
  [[ -d "${DEPLOY_ROOT}/.git" ]]
}

current_commit() {
  git -C "$DEPLOY_ROOT" rev-parse HEAD
}

save_previous_commit() {
  is_git_repo || return 0
  current_commit > "${DEPLOY_STATE_DIR}/previous-commit"
  log "Saved rollback point: $(cat "${DEPLOY_STATE_DIR}/previous-commit")"
}

backup_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    local dest="${DEPLOY_STATE_DIR}/backups/.env.$(timestamp)"
    cp -a "$ENV_FILE" "$dest"
    chmod 600 "$dest"
    echo "$dest" > "${DEPLOY_STATE_DIR}/latest-env-backup"
    log "Backed up .env to $dest"
  else
    warn "No .env at $ENV_FILE to back up"
  fi
}

backup_full_installation() {
  local label="${1:-snapshot}"
  local dest="${BACKUP_ROOT}/${label}-$(timestamp)"
  mkdir -p "$BACKUP_ROOT"
  if [[ -d "$DEPLOY_ROOT" ]]; then
    run cp -a "$DEPLOY_ROOT" "$dest"
    log "Full installation backup: $dest"
    echo "$dest" > "${DEPLOY_STATE_DIR}/latest-full-backup"
  fi
}

preserve_runtime_artifacts() {
  # Copy .env, venv, and .cache from SRC into DEST (used during migration).
  local src="$1"
  local dest="$2"

  if [[ -f "${src}/.env" ]]; then
    cp -a "${src}/.env" "${dest}/.env"
    chmod 600 "${dest}/.env"
    log "Preserved .env"
  else
    warn "No .env found at ${src}/.env — create one before going live"
  fi

  if [[ -d "${src}/venv" ]]; then
    rm -rf "${dest}/venv"
    cp -a "${src}/venv" "${dest}/venv"
    log "Preserved virtual environment"
  fi

  if [[ -d "${src}/.cache" ]]; then
    mkdir -p "${dest}/.cache"
    cp -a "${src}/.cache/." "${dest}/.cache/"
    log "Preserved .cache (Telegram sent-store, etc.)"
  fi
}

install_dependencies() {
  [[ -d "$DEPLOY_ROOT" ]] || die "Deploy root missing: $DEPLOY_ROOT"
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    log "Creating virtual environment at $VENV_DIR"
    run python3 -m venv "$VENV_DIR"
  fi
  run "${VENV_DIR}/bin/pip" install --upgrade pip
  run "${VENV_DIR}/bin/pip" install -e "${DEPLOY_ROOT}"
}

ensure_systemd_service() {
  local unit_src="${DEPLOY_ROOT}/deploy/systemd/${SERVICE_NAME}.service"
  if [[ -f "$SYSTEMD_UNIT" && "${FORCE_SYSTEMD:-0}" != "1" ]]; then
    log "systemd unit already exists — preserving $SYSTEMD_UNIT"
    return 0
  fi
  [[ -f "$unit_src" ]] || die "Service template missing: $unit_src"
  run cp "$unit_src" "$SYSTEMD_UNIT"
  run systemctl daemon-reload
  run systemctl enable "$SERVICE_NAME"
  log "Installed systemd unit $SYSTEMD_UNIT"
}

restart_service() {
  if [[ ! -f "$SYSTEMD_UNIT" ]]; then
    warn "No systemd unit at $SYSTEMD_UNIT — skipping restart"
    return 0
  fi
  run systemctl restart "$SERVICE_NAME"
}

verify_service() {
  if [[ ! -f "$SYSTEMD_UNIT" ]]; then
    warn "No systemd unit — skipping service verification"
    return 0
  fi

  local elapsed=0
  while (( elapsed < VERIFY_TIMEOUT_SECONDS )); do
    if systemctl is-active --quiet "$SERVICE_NAME"; then
      log "Service $SERVICE_NAME is active"
      break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  systemctl is-active --quiet "$SERVICE_NAME" || {
    systemctl status "$SERVICE_NAME" --no-pager -l | head -30 >&2 || true
    return 1
  }

  # Import smoke test — confirms venv + package layout.
  run env PYTHONPATH="$DEPLOY_ROOT" "${VENV_DIR}/bin/python" -c \
    "from app.services.signal_service import SignalService; print('import_ok')"
  log "Python import verification passed"
  return 0
}

install_system_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    run apt-get update -qq
    run apt-get install -y -qq git python3 python3-venv python3-pip ca-certificates
    update-ca-certificates || true
  elif command -v dnf >/dev/null 2>&1; then
    run dnf install -y git python3 python3-pip
  elif command -v yum >/dev/null 2>&1; then
    run yum install -y git python3 python3-pip
  else
    warn "Could not auto-install packages — ensure git, python3, and venv are available"
  fi
}

clone_repository() {
  local dest="$1"
  mkdir -p "$(dirname "$dest")"
  if [[ -d "$dest" ]]; then
    die "Clone destination already exists: $dest"
  fi
  log "Cloning $GIT_REPO (branch $GIT_BRANCH) -> $dest"
  run git clone --branch "$GIT_BRANCH" --single-branch "$GIT_REPO" "$dest"
}

configure_git_safe_directory() {
  # Avoid 'dubious ownership' when deploying as root from /opt.
  git config --global --add safe.directory "$DEPLOY_ROOT" 2>/dev/null || true
}

print_deploy_summary() {
  cat <<EOF

========================================
 Deployment summary
========================================
 Path    : $DEPLOY_ROOT
 Branch  : $GIT_BRANCH
 Service : $SERVICE_NAME
 Backups : $BACKUP_ROOT
 State   : $(deployment_state)
========================================
 Logs    : journalctl -u $SERVICE_NAME -f
 Status  : systemctl status $SERVICE_NAME
 Update  : bash $DEPLOY_ROOT/scripts/deploy/update.sh
 Rollback: bash $DEPLOY_ROOT/scripts/deploy/rollback.sh
========================================
EOF
}
