# Structure Persistence — Post-Implementation Report

## Problem (why BOS/CHOCH was too strict)

| Issue | Old behavior |
|-------|----------------|
| **Instantaneous BOS** | Only true when *current* close breaks last swing — lost after any pullback |
| **Instantaneous CHOCH** | Same — single-bar detection, no memory |
| **HTF trend** | Recomputed each scan; brief SIDEWAYS wiped directional bias |
| **LTF trend** | EMA-only; ignored UPTREND/DOWNTREND structure |

Result: **100% HTF/BOS/CHOCH failure** in ranging/pullback conditions.

## Solution

New module: `app/analysis/structure_persistence.py`

- **Closed-bar only** — uses `df.iloc[:i+1]` per bar (no look-ahead, no repainting)
- **Configurable lookback** via env:
  - `STRUCTURE_BOS_LOOKBACK` (default 12)
  - `STRUCTURE_CHOCH_LOOKBACK` (default 12)
  - `STRUCTURE_HTF_LOOKBACK` (default 8)
- **HTF invalidation** — bullish bias clears on close below recent HTF swing low (and vice versa)
- **LTF trend** — `resolve_ltf_trend()` maps UPTREND→BULLISH, DOWNTREND→BEARISH when EMA is sideways

**Unchanged:** confidence scoring, risk manager, Telegram formatter, ADX/RSI/ATR filters.

---

## Diagnostic results (48 cycles × 5 symbols = 240 scans)

See `docs/MULTI_CYCLE_DIAGNOSTIC_REPORT.md` for latest numbers.

### Before vs after (single scan snapshot)

| Symbol | HTF | BOS | CHOCH | Confidence (before→after) |
|--------|-----|-----|-------|----------------------------|
| ETHUSDT | FAIL→**PASS** | FAIL→**PASS** | FAIL→**PASS** | 12→**39** |
| DOGEUSDT | FAIL→**PASS** | FAIL | FAIL | 12→**46** |
| XRPUSDT | FAIL | FAIL→**PASS** | FAIL→**PASS** | 10→**30** |
| BTCUSDT | FAIL→**PASS** | FAIL | FAIL | 22→22 |

Primary blocker shifted from **HTF 100%** → **Order Block / confluence count**.

---

## VPS deploy

```bash
export DEPLOY_SSH=root@YOUR_VPS_IP
./scripts/deploy/contabo_deploy.sh
```

After 2 hours:

```bash
bash /opt/ai-trading-system/scripts/vps_collect_diagnostics.sh
python3 scripts/run_diagnostic_cycles.py 48  # optional replay
```

---

## Tuning

Increase persistence (more signals, older structure):

```env
STRUCTURE_BOS_LOOKBACK=16
STRUCTURE_CHOCH_LOOKBACK=16
STRUCTURE_HTF_LOOKBACK=12
```

Decrease (stricter, fresher structure only):

```env
STRUCTURE_BOS_LOOKBACK=8
```
