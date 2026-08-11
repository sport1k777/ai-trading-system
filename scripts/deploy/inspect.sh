#!/usr/bin/env bash
# Inspect VPS deployment state (run ON THE VPS or via SSH).
#
#   ssh root@YOUR_VPS 'bash -s' < scripts/deploy/inspect.sh
#   sudo bash /opt/ai-trading-system/scripts/deploy/inspect.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

echo "========================================"
echo " AI Trading System — Deploy Inspector"
echo "========================================"
echo "DEPLOY_ROOT : $DEPLOY_ROOT"
echo "BACKUP_ROOT : $BACKUP_ROOT"
echo "SERVICE_NAME: $SERVICE_NAME"
echo "GIT_REPO    : $GIT_REPO"
echo "GIT_BRANCH  : $GIT_BRANCH"
echo "----------------------------------------"

state="$(deployment_state)"
echo "Deployment state: $state"

if [[ -d "$DEPLOY_ROOT" ]]; then
  echo "Install path exists: yes"
  echo "pyproject.toml     : $([[ -f "${DEPLOY_ROOT}/pyproject.toml" ]] && echo yes || echo no)"
  echo ".env               : $([[ -f "${DEPLOY_ROOT}/.env" ]] && echo yes || echo no)"
  echo "venv               : $([[ -d "${DEPLOY_ROOT}/venv" ]] && echo yes || echo no)"
  echo ".cache             : $([[ -d "${DEPLOY_ROOT}/.cache" ]] && echo yes || echo no)"
  echo ".git               : $([[ -d "${DEPLOY_ROOT}/.git" ]] && echo yes || echo no)"
else
  echo "Install path exists: no"
fi

if is_git_repo; then
  echo "----------------------------------------"
  echo "Git branch : $(git -C "$DEPLOY_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "Git commit : $(git -C "$DEPLOY_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  if [[ -f "${DEPLOY_STATE_DIR}/previous-commit" ]]; then
    echo "Rollback to: $(cat "${DEPLOY_STATE_DIR}/previous-commit")"
  fi
fi

echo "----------------------------------------"
if [[ -f "$SYSTEMD_UNIT" ]]; then
  echo "systemd unit : $SYSTEMD_UNIT (present)"
  systemctl is-enabled "$SERVICE_NAME" 2>/dev/null && echo "enabled: yes" || echo "enabled: no"
  systemctl is-active "$SERVICE_NAME" 2>/dev/null && echo "active : yes" || echo "active : no"
else
  echo "systemd unit : not installed"
fi

if [[ -d "$BACKUP_ROOT" ]]; then
  echo "----------------------------------------"
  echo "Backups in $BACKUP_ROOT:"
  ls -1dt "${BACKUP_ROOT}"/* 2>/dev/null | head -5 || echo "(none)"
fi

echo "========================================"
case "$state" in
  none)   echo "Next step: run scripts/deploy/deploy.sh (fresh install)" ;;
  manual) echo "Next step: run scripts/deploy/deploy.sh (migrate to Git)" ;;
  git)    echo "Next step: run scripts/deploy/update.sh (routine update)" ;;
esac
echo "========================================"
