# Git-Based VPS Deployment

Migrate from manual/rsync deployment to Git-managed updates **without deleting** the existing VPS installation.

## Overview

| Script | Purpose |
|--------|---------|
| `scripts/deploy/inspect.sh` | Detect current VPS state (none / manual / git) |
| `scripts/deploy/deploy.sh` | First-time clone **or** safe migration from manual install |
| `scripts/deploy/update.sh` | Routine `git pull` + dependency install + service restart |
| `scripts/deploy/rollback.sh` | Restore the previous commit if an update fails |

All scripts run **on the VPS as root**. They preserve:

- `.env` (Bybit + Telegram credentials)
- `venv/` (reused; dependencies refreshed with `pip install -e .`)
- `.cache/` (Telegram sent-signal store)
- Existing `systemd` unit (unless `FORCE_SYSTEMD=1`)

Backups are stored under `/opt/ai-trading-system-backups/`.

---

## Step 1 — Inspect the VPS

SSH into the server and detect the current state.

### Option A — from your laptop

```bash
ssh root@YOUR_VPS_IP 'bash -s' < scripts/deploy/inspect.sh
```

### Option B — on the VPS (manual install already present)

```bash
sudo bash /opt/ai-trading-system/scripts/deploy/inspect.sh
```

Expected `Deployment state` values:

| State | Meaning |
|-------|---------|
| `none` | No install at `/opt/ai-trading-system` |
| `manual` | Files exist but **no** `.git` directory (rsync/scp deploy) |
| `git` | Already Git-managed |

---

## Step 2 — One-time migration (`deploy.sh`)

### Case A — manual/rsync install already running (most common)

The script will:

1. Copy the full tree to `/opt/ai-trading-system-backups/pre-git-migration-<timestamp>/`
2. Clone GitHub into a staging directory
3. Copy `.env`, `venv/`, and `.cache/` into the clone
4. Move the old tree to `/opt/ai-trading-system-backups/active-manual-<timestamp>/` (**not deleted**)
5. Promote the Git clone to `/opt/ai-trading-system`
6. Reinstall dependencies, restart `ai-trading-signals`, verify

```bash
ssh root@YOUR_VPS_IP

# Optional configuration
export GIT_BRANCH=cursor/ai-signal-engine-production

sudo bash /opt/ai-trading-system/scripts/deploy/deploy.sh
```

### Case B — fresh VPS (no existing install)

Bootstrap the deploy script, then run it:

```bash
ssh root@YOUR_VPS_IP

git clone --branch cursor/ai-signal-engine-production --depth 1 \
  https://github.com/sport1k777/ai-trading-system.git /tmp/ai-trading-bootstrap

export GIT_BRANCH=cursor/ai-signal-engine-production
sudo bash /tmp/ai-trading-bootstrap/scripts/deploy/deploy.sh
```

After deploy, edit credentials if needed:

```bash
sudo nano /opt/ai-trading-system/.env
sudo chmod 600 /opt/ai-trading-system/.env
sudo systemctl restart ai-trading-signals
```

### Case C — already a Git repository

`deploy.sh` is idempotent: it refreshes dependencies, preserves `.env` and systemd, and restarts the service. Use `update.sh` for routine pulls.

---

## Step 3 — Routine updates (`update.sh`)

After migration, deploy new commits from GitHub:

```bash
ssh root@YOUR_VPS_IP

export GIT_BRANCH=cursor/ai-signal-engine-production   # optional if default is fine
sudo bash /opt/ai-trading-system/scripts/deploy/update.sh
```

`update.sh` will:

1. Save the current commit to `.deploy/previous-commit` (rollback point)
2. Back up `.env` to `.deploy/backups/.env.<timestamp>`
3. `git fetch` + `git pull --ff-only`
4. `pip install -e .` inside the existing `venv`
5. `systemctl restart ai-trading-signals`
6. Verify the service is active and Python imports succeed

If verification fails, `update.sh` attempts an automatic rollback.

---

## Step 4 — Rollback (`rollback.sh`)

Restore the deployment to the commit saved before the last update:

```bash
ssh root@YOUR_VPS_IP
sudo bash /opt/ai-trading-system/scripts/deploy/rollback.sh
```

Rollback to a specific commit:

```bash
export ROLLBACK_COMMIT=fe31639
sudo bash /opt/ai-trading-system/scripts/deploy/rollback.sh
```

Non-interactive (used internally when update verification fails):

```bash
sudo bash /opt/ai-trading-system/scripts/deploy/rollback.sh --auto
```

---

## Configuration

Copy the example env file on the VPS for persistent settings:

```bash
sudo mkdir -p /etc/ai-trading
sudo cp /opt/ai-trading-system/scripts/deploy/deploy.env.example /etc/ai-trading/deploy.env
sudo nano /etc/ai-trading/deploy.env
```

Source before any deploy command:

```bash
set -a && source /etc/ai-trading/deploy.env && set +a
sudo -E bash /opt/ai-trading-system/scripts/deploy/update.sh
```

| Variable | Default | Description |
|----------|---------|-------------|
| `GIT_REPO` | `https://github.com/sport1k777/ai-trading-system.git` | Remote URL |
| `GIT_BRANCH` | `cursor/ai-signal-engine-production` | Branch to deploy |
| `DEPLOY_ROOT` | `/opt/ai-trading-system` | Application path |
| `BACKUP_ROOT` | `/opt/ai-trading-system-backups` | Backup storage |
| `SERVICE_NAME` | `ai-trading-signals` | systemd unit name |
| `FORCE_SYSTEMD` | `0` | Set `1` to overwrite existing unit file |

---

## Verification commands

```bash
# Service health
systemctl status ai-trading-signals
systemctl is-active ai-trading-signals

# Live logs
journalctl -u ai-trading-signals -f

# Deploy state
cat /opt/ai-trading-system/.deploy/previous-commit   # rollback target
cat /opt/ai-trading-system/.deploy/current-commit    # last successful deploy

# Git revision on VPS
git -C /opt/ai-trading-system rev-parse --short HEAD
git -C /opt/ai-trading-system log -1 --oneline

# Telegram smoke test
cd /opt/ai-trading-system
PYTHONPATH=. ./venv/bin/python scripts/telegram_test.py
```

---

## Backup layout

```
/opt/ai-trading-system-backups/
├── pre-git-migration-20260710-120000/   # full tree before migration
├── active-manual-20260710-120100/       # retired manual install
└── ...

/opt/ai-trading-system/.deploy/
├── previous-commit                      # rollback SHA
├── current-commit                       # last good SHA
├── latest-env-backup                    # path to latest .env copy
└── backups/
    └── .env.20260710-120000
```

---

## Migration from `contabo_deploy.sh` (rsync)

The legacy laptop-side rsync deploy (`scripts/deploy/contabo_deploy.sh`) remains available as a fallback. After Git migration:

1. Run `deploy.sh` once on the VPS (preserves `.env`, `venv`, systemd).
2. Use `update.sh` for all future releases.
3. Keep rsync deploy only for emergency recovery.

Recommended workflow after migration:

```bash
# Local — push changes
git push origin cursor/ai-signal-engine-production

# VPS — pull and restart
ssh root@YOUR_VPS_IP 'bash /opt/ai-trading-system/scripts/deploy/update.sh'
```

---

## Troubleshooting

### `git pull` fails (non-fast-forward)

Local VPS changes conflict with remote. Inspect:

```bash
cd /opt/ai-trading-system
git status
git log --oneline -3
```

Fix by resetting to remote (discards local commits on VPS):

```bash
git fetch origin
git reset --hard origin/cursor/ai-signal-engine-production
bash scripts/deploy/update.sh
```

Or rollback:

```bash
bash scripts/deploy/rollback.sh
```

### Service fails after update

```bash
journalctl -u ai-trading-signals -n 80 --no-pager
bash /opt/ai-trading-system/scripts/deploy/rollback.sh
```

### Private GitHub repository

Configure SSH deploy keys on the VPS:

```bash
ssh-keygen -t ed25519 -f /root/.ssh/github_deploy -N ""
cat /root/.ssh/github_deploy.pub   # add as deploy key on GitHub

export GIT_REPO=git@github.com:sport1k777/ai-trading-system.git
```

### `.env` missing after migration

Restore from backup:

```bash
cp /opt/ai-trading-system/.deploy/backups/.env.* /opt/ai-trading-system/.env
chmod 600 /opt/ai-trading-system/.env
systemctl restart ai-trading-signals
```

---

## Security notes

- Never commit `.env` to Git (it is in `.gitignore`).
- Keep `.env` mode `600`.
- Deploy scripts must run as root because the systemd unit runs as root today.
- Review `deploy/systemd/ai-trading-signals.service` before enabling `FORCE_SYSTEMD=1`.
