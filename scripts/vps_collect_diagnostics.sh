#!/usr/bin/env bash
# Collect signal-service diagnostic logs from a running VPS.
# Run ON the VPS (or via ssh once connected):
#   bash /opt/ai-trading-system/scripts/vps_collect_diagnostics.sh
#
# Optional env:
#   SERVICE_NAME=ai-trading-signals
#   LINES=2000
#   OUT=/opt/ai-trading-system/docs/VPS_DIAGNOSTIC_LOGS.txt

set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-ai-trading-signals}"
LINES="${LINES:-2000}"
OUT="${OUT:-/opt/ai-trading-system/docs/VPS_DIAGNOSTIC_LOGS.txt}"

mkdir -p "$(dirname "$OUT")"

{
  echo "=== VPS Diagnostic Log Export ==="
  echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "Service: $SERVICE_NAME"
  echo ""

  echo "=== Service status ==="
  systemctl status "$SERVICE_NAME" --no-pager -l | head -25 || true
  echo ""

  echo "=== Recent scan diagnostics ==="
  journalctl -u "$SERVICE_NAME" -n "$LINES" --no-pager \
    | awk '/Scan diagnostic/{show=1; blank=0} show{ if ($0 ~ /^$/) { blank++; if (blank>2) show=0 } else { blank=0; print } }'

  echo ""
  echo "=== One-shot pipeline diagnostic ==="
  cd /opt/ai-trading-system
  PYTHONPATH=. ./venv/bin/python scripts/signal_pipeline_diagnostic.py 2>&1 || true
} | tee "$OUT"

echo ""
echo "Saved to $OUT"
