#!/usr/bin/env bash
# Safe first-time or migration deploy on the VPS.
#
# - Does NOT delete the existing manual/rsync installation (full backup kept).
# - Detects whether $DEPLOY_ROOT is already a Git repository.
# - Preserves .env, venv, .cache, and an existing systemd unit.
#
# Run ON THE VPS as root:
#   sudo bash /opt/ai-trading-system/scripts/deploy/deploy.sh
#
# Or before clone exists (bootstrap):
#   curl -fsSL .../deploy.sh | sudo bash -s
#
# Environment overrides (optional):
#   GIT_REPO, GIT_BRANCH, DEPLOY_ROOT, BACKUP_ROOT, SERVICE_NAME

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

main() {
  require_root
  require_commands git python3 systemctl
  ensure_dirs

  local state
  state="$(deployment_state)"

  log "Deployment state: $state"
  log "Target path: $DEPLOY_ROOT"

  install_system_packages

  case "$state" in
    git)
      deploy_existing_git_repo
      ;;
    manual)
      migrate_manual_installation
      ;;
    none)
      deploy_fresh_installation
      ;;
    *)
      die "Unknown deployment state: $state"
      ;;
  esac
}

deploy_existing_git_repo() {
  log "Git repository already present — ensuring dependencies and service"
  configure_git_safe_directory
  cd "$DEPLOY_ROOT"
  backup_env_file
  install_dependencies
  ensure_systemd_service
  restart_service
  verify_service || die "Service verification failed after deploy"
  print_deploy_summary
  log "Already under Git control. Use scripts/deploy/update.sh for future updates."
}

migrate_manual_installation() {
  log "Manual installation detected — migrating to Git without deleting the original"

  backup_full_installation "pre-git-migration"
  backup_env_file

  local staging="${DEPLOY_ROOT}.git-staging.$$"
  local retired="${BACKUP_ROOT}/active-manual-$(timestamp)"

  trap 'rm -rf "$staging"' EXIT

  clone_repository "$staging"
  preserve_runtime_artifacts "$DEPLOY_ROOT" "$staging"

  log "Retiring manual tree to $retired (original also in pre-git-migration backup)"
  run mv "$DEPLOY_ROOT" "$retired"
  run mv "$staging" "$DEPLOY_ROOT"
  trap - EXIT

  configure_git_safe_directory
  cd "$DEPLOY_ROOT"
  install_dependencies
  ensure_systemd_service
  save_previous_commit
  restart_service
  verify_service || {
    warn "Verification failed — manual install preserved at $retired"
    warn "Run: bash $DEPLOY_ROOT/scripts/deploy/rollback.sh"
    exit 1
  }

  print_deploy_summary
  log "Migration complete. Manual install retained at:"
  log "  $retired"
  log "  $(cat "${DEPLOY_STATE_DIR}/latest-full-backup" 2>/dev/null || echo '(see BACKUP_ROOT)')"
}

deploy_fresh_installation() {
  log "No existing installation — performing fresh Git clone"

  local parent
  parent="$(dirname "$DEPLOY_ROOT")"
  mkdir -p "$parent"

  clone_repository "$DEPLOY_ROOT"
  configure_git_safe_directory
  cd "$DEPLOY_ROOT"

  if [[ ! -f "$ENV_FILE" ]]; then
    warn "No .env found — copy credentials before starting the service"
    if [[ -f "${DEPLOY_ROOT}/.env.example" ]]; then
      cp "${DEPLOY_ROOT}/.env.example" "$ENV_FILE"
      chmod 600 "$ENV_FILE"
      warn "Created $ENV_FILE from .env.example — edit with real credentials"
    fi
  fi

  install_dependencies
  ensure_systemd_service
  save_previous_commit
  restart_service
  verify_service || die "Service verification failed after fresh deploy"
  print_deploy_summary
}

main "$@"
