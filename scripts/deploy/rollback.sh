#!/usr/bin/env bash
# Restore the previous Git deployment if an update fails.
#
# - Checks out the commit saved in .deploy/previous-commit
# - Reinstalls dependencies in the preserved venv
# - Restores the latest .env backup if the working copy lost it
# - Restarts and verifies systemd service
#
# Run ON THE VPS as root:
#   sudo bash /opt/ai-trading-system/scripts/deploy/rollback.sh
#   sudo bash /opt/ai-trading-system/scripts/deploy/rollback.sh --auto
#
# Optional:
#   ROLLBACK_COMMIT=<sha> sudo bash .../rollback.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

AUTO_MODE=0
if [[ "${1:-}" == "--auto" ]]; then
  AUTO_MODE=1
fi

main() {
  require_root
  require_commands git python3 systemctl
  ensure_dirs

  is_git_repo || die "No Git repository at $DEPLOY_ROOT — nothing to roll back"

  configure_git_safe_directory
  cd "$DEPLOY_ROOT"

  local target_commit
  if [[ -n "${ROLLBACK_COMMIT:-}" ]]; then
    target_commit="$ROLLBACK_COMMIT"
  elif [[ -f "${DEPLOY_STATE_DIR}/previous-commit" ]]; then
    target_commit="$(cat "${DEPLOY_STATE_DIR}/previous-commit")"
  else
    die "No rollback commit found. Set ROLLBACK_COMMIT or run update.sh first."
  fi

  local current_commit
  current_commit="$(current_commit)"

  if [[ "$current_commit" == "$target_commit" ]]; then
    log "Already at rollback target $target_commit"
    verify_service && exit 0
    die "Service unhealthy at rollback target — manual intervention required"
  fi

  if [[ "$AUTO_MODE" -eq 0 ]]; then
    log "Rolling back: $current_commit -> $target_commit"
    read -r -p "Continue? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || die "Rollback cancelled"
  else
    log "Auto-rollback: $current_commit -> $target_commit"
  fi

  backup_env_file
  echo "$current_commit" > "${DEPLOY_STATE_DIR}/failed-commit"

  run git fetch origin "$GIT_BRANCH"
  run git checkout "$target_commit"
  # Return branch pointer for future updates without forcing a divergent branch.
  git checkout -B "$GIT_BRANCH" "$target_commit" 2>/dev/null || true

  if [[ ! -f "$ENV_FILE" && -f "${DEPLOY_STATE_DIR}/latest-env-backup" ]]; then
    local env_backup
    env_backup="$(cat "${DEPLOY_STATE_DIR}/latest-env-backup")"
    if [[ -f "$env_backup" ]]; then
      cp -a "$env_backup" "$ENV_FILE"
      chmod 600 "$ENV_FILE"
      log "Restored .env from $env_backup"
    fi
  fi

  install_dependencies
  restart_service

  if ! verify_service; then
    die "Rollback completed but service verification failed — check journalctl -u $SERVICE_NAME"
  fi

  echo "$target_commit" > "${DEPLOY_STATE_DIR}/current-commit"
  log "Rollback successful — now at $target_commit"
  print_deploy_summary
}

main "$@"
