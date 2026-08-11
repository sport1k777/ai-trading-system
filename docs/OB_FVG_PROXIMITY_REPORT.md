# Post OB/FVG Proximity Deploy Report

**Change:** `app/analysis/poi_proximity.py` — 0.3% tolerance on OB/FVG boundaries  
**Commit:** `03c9419`  
**VPS deploy:** ❌ Blocked — SSH `Permission denied` to `root@13.140.161.100`

---

## Deploy manually on VPS

```bash
ssh -i ~/.ssh/id_ed25519 root@YOUR_VPS_IP
cd /opt/ai-trading-system
git pull origin cursor/ai-signal-engine-production
./venv/bin/pip install -e .
systemctl restart ai-trading-signals
systemctl status ai-trading-signals
```

After **2 hours**:

```bash
bash /opt/ai-trading-system/scripts/vps_collect_diagnostics.sh
# writes docs/VPS_DIAGNOSTIC_LOGS.txt + VPS_DIAGNOSTIC_SUMMARY.md
```

---

## Interim report (120 live scans, post-change)

Collected locally via `scripts/run_diagnostic_cycles.py 24` (24 cycles × 5 symbols).

| Metric | Value |
|--------|-------|
| Total scans | **120** |
| Signals generated | **0** |
| Telegram-eligible | **0** |
| Order Block PASS | **26/120 (22%)** |
| FVG PASS | **23/120 (19%)** |

### Confidence distribution

| Bucket | Count |
|--------|-------|
| 0–19 | 50 |
| 20–39 | 70 |
| 40–59 | 0 |
| 60–79 | 0 |
| 80–100 | 0 |

**min:** 0.0 | **max:** 34.0 | **avg:** 18.1

### Rejection reasons (100% of scans)

- `Rejected because HTF failed` — **120/120**

No scan reached engine emit threshold (65 confidence, 5 factors).

### Sample improvement (DOGEUSDT)

After proximity fix, a single scan shows:

```
Order Block: PASS
FVG: PASS
Confidence score: 34.0  (was ~12.0 before)
```

OB/FVG proximity fix **works** — confluence improved but remains below engine gate.

---

## Bottleneck (unchanged)

Primary blocker is still **HTF / trend / BOS / CHOCH / EMA** — not OB/FVG.

Next minimal fix (when approved): structure event persistence (BOS/liquidity lookback).

---

## Thresholds unchanged

✅ `PRO_MIN_CONFIDENCE` (65)  
✅ `TELEGRAM_NOTIFY_MIN_CONFIDENCE` (90)  
✅ ADX, RSI, ATR, HTF bias, scoring, grading — untouched
