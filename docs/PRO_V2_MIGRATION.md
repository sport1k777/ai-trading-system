# Signal Engine PRO V2 — Migration Guide

## Overview

PRO V2 introduces a **sequential Smart Money narrative engine** with hard gates, HTF bias, premium/discount zones, graded signals (A+/A/B/C), and Risk Manager V2.

PRO V1 remains available as the default fallback.

## Enable PRO V2

```env
SIGNAL_ENGINE_VERSION=v2
TELEGRAM_NOTIFY_MIN_CONFIDENCE=85
PRO_V2_MIN_GRADE=A
```

## Rollback to V1

```env
SIGNAL_ENGINE_VERSION=v1
```

Restart the systemd service:

```bash
systemctl restart ai-trading-signals
```

## Key differences

| Feature | PRO V1 | PRO V2 |
|---|---|---|
| Logic | 8-condition checklist | Sequential narrative |
| HTF | None | 1h bias + resampled fallback |
| Premium/Discount | No | Yes |
| Grading | Confidence only | A+/A/B/C |
| Risk | Single TP | TP1/TP2/TP3 via liquidity |
| Min R:R gate | No | Yes (default 2.0) |
| Repaint guard | Partial | Closed-bar analysis |

## VPS deployment checklist

1. `rsync` updated project to `/opt/ai-trading-system`
2. Set `SIGNAL_ENGINE_VERSION=v2` in `.env`
3. `pip install -e .` in venv
4. `pytest` passes
5. `python scripts/pro_v2_eval.py` for local backtest report
6. `systemctl restart ai-trading-signals`
7. `journalctl -u ai-trading-signals -f` — verify scans
8. Confirm Telegram test: `python scripts/telegram_test.py`

## Shadow mode (recommended)

Run v2 in production with elevated Telegram threshold first:

```env
SIGNAL_ENGINE_VERSION=v2
TELEGRAM_NOTIFY_MIN_CONFIDENCE=90
PRO_V2_MIN_GRADE=A
```

Monitor `gates_failed` in logs for 48h before lowering thresholds.
