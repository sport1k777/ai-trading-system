#!/usr/bin/env bash
# Routine Git-based update on the VPS.
#
# - git pull (fast-forward only)
# - reinstall dependencies in the existing venv
# - restart + verify systemd service
# - records a rollback point before pulling
#
# Run ON THE VPS as root:
#   sudo bash /opt/ai-trading-system/scripts/deploy/update.sh
#
# Environment overrides:
#   GIT_BRANCH, DEPLOY_ROOT, SERVICE_NAME

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

main() {
  require_root
  require_commands git python3 systemctl
  ensure_dirs

  is_git_repo || die \
    "No Git repository at $DEPLOY_ROOT. Run scripts/deploy/deploy.sh to migrate first."

  configure_git_safe_directory
  cd "$DEPLOY_ROOT"

  local before_branch before_commit
  before_branch="$(git rev-parse --abbrev-ref HEAD)"
  before_commit="$(current_commit)"

  log "Updating $DEPLOY_ROOT"
  log "Current commit: $before_commit ($before_branch)"

  save_previous_commit
  backup_env_file
  echo "$before_commit" > "${DEPLOY_STATE_DIR}/last-update-attempt"
  echo "$(timestamp)" > "${DEPLOY_STATE_DIR}/last-update-time"

  run git fetch origin "$GIT_BRANCH"
  if ! git merge-base --is-ancestor HEAD "origin/${GIT_BRANCH}" 2>/dev/null; then
    warn "Local branch has diverged from origin/${GIT_BRANCH}"
  fi

  if ! run git pull --ff-only origin "$GIT_BRANCH"; then
    die "git pull failed (non-fast-forward). Resolve manually or run rollback.sh"
  fi

  local after_commit
  after_commit="$(current_commit)"
  log "Updated to commit: $after_commit"

  install_dependencies
  restart_service

  if ! verify_service; then
    warn "Service verification failed after update"
    warn "Attempting automatic rollback to $before_commit"
    if bash "${SCRIPT_DIR}/rollback.sh" --auto; then
      die "Update rolled back automatically — inspect logs and fix upstream before retrying"
    fi
    die "Update failed and automatic rollback did not succeed — run rollback.sh manually"
  fi

  echo "$after_commit" > "${DEPLOY_STATE_DIR}/current-commit"
  log "Update successful"
  print_deploy_summary
}

main "$@"
