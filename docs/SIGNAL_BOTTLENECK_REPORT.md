# Signal Pipeline Bottleneck Report

**Generated:** 2026-07-10 (live Bybit scan, engine v1, 15m)  
**VPS deploy:** Blocked — SSH key not accepted from this environment (`root@13.140.161.100`). Deploy manually (see below).

---

## Deploy diagnostic logging to VPS

From your Mac (after SSH works):

```bash
export DEPLOY_SSH=root@YOUR_VPS_IP
export DEPLOY_KEY=~/.ssh/id_ed25519
./scripts/deploy/contabo_deploy.sh
```

Or on the VPS after `git pull`:

```bash
cd /opt/ai-trading-system
git pull
./venv/bin/pip install -e .
systemctl restart ai-trading-signals
bash scripts/vps_collect_diagnostics.sh
```

Every scan now logs at **INFO**:

```
BTCUSDT
HTF bias: FAIL (...)
Market structure: RANGE
BOS: FAIL (...)
...
Confidence score: 22.0
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: ...
```

View live logs:

```bash
journalctl -u ai-trading-signals -f | grep -A 15 "Scan diagnostic"
```

---

## Live scan results (5 symbols)

| Symbol | Structure | Confidence | Final decision | Primary rejection |
|--------|-----------|------------|----------------|-------------------|
| BTCUSDT | RANGE | 22.0 | WAIT | HTF + BOS + CHOCH + confluence 22/65 |
| ETHUSDT | UPTREND | 12.0 | WAIT | HTF + BOS + CHOCH + confluence 12/65 |
| SOLUSDT | DOWNTREND | 0.0 | WAIT | ATR gate 6.39% + HTF + BOS |
| XRPUSDT | RANGE | 10.0 | WAIT | HTF + BOS + ADX 20.3 + confluence 10/65 |
| DOGEUSDT | UPTREND | 12.0 | WAIT | HTF + BOS + liquidity + confluence 12/65 |

**Engine signals:** 0/5  
**Telegram-eligible:** 0/5  

---

## Bottleneck frequency (5 scans)

| Check | Failed |
|-------|--------|
| HTF bias | **5/5 (100%)** |
| BOS | **5/5 (100%)** |
| CHOCH | **5/5 (100%)** |
| EMA filter | **5/5 (100%)** |
| Order Block | 4/5 (80%) |
| FVG | 3/5 (60%) |
| RSI | 2/5 (40%) |
| ADX | 2/5 (40%) |
| Liquidity sweep | 1/5 (20%) |
| ATR | 1/5 (20%) |

---

## Root cause (not a confidence bug)

Three compounding filters block **all** signals:

### 1. Trend stuck at SIDEWAYS (100% HTF/EMA failure)

`TrendAnalyzer` returns `SIDEWAYS` on every symbol. That disables:
- HTF bias proxy
- EMA trend condition
- Directional confluence accumulation

Even symbols with `UPTREND`/`DOWNTREND` **structure** still show `SIDEWAYS` **trend**.

### 2. BOS/CHOCH require instantaneous break (100% failure)

`BOSAnalyzer` only returns BOS when **the current close** is beyond the last swing. After a break and pullback, BOS reverts to `NO_BOS`. No persistence.

Same for `LiquidityAnalyzer` — only checks the **last closed bar** for a sweep. Sweeps 2–5 bars ago are invisible.

### 3. Confluence gate requires 5 simultaneous factors at 65% score

Best score observed: **22%**. With 100% structure failures, the engine never reaches `PRO_MIN_CONDITIONS=5`.

**Telegram 90% gate is not the bottleneck** — the engine never produces a signal.

---

## Minimal code change to restore signal frequency

**Do not lower `PRO_MIN_CONFIDENCE` or `TELEGRAM_NOTIFY_MIN_CONFIDENCE`.**

### Change 1 — Structure event persistence (highest impact)

**Files:** `app/analysis/bos.py`, `app/analysis/choch.py`, `app/analysis/liquidity.py`

Add lookback (8–12 closed bars): if a BOS, CHOCH, or liquidity sweep occurred recently, keep it active until structure invalidates.

```python
# bos.py — detect most recent break within lookback, not only last bar
for i in range(len(df) - lookback, len(df)):
    if close[i] > last_swing_high:
        return "BULLISH_BOS"
```

**Why:** Sweeps and breaks are valid setup context for several bars after the event. Current code forgets them immediately, causing 100% BOS/liquidity failure in live scans.

### Change 2 — Align trend with structure in RANGE/weak ADX regimes

**File:** `app/analysis/pro/conditions.py` → `evaluate_ema_trend`

When `structure` is `UPTREND`/`DOWNTREND` but `trend` is `SIDEWAYS`, allow EMA condition if price aligns with structure direction.

**Why:** 5/5 scans fail EMA because trend says SIDEWAYS while structure often shows UPTREND/DOWNTREND.

### Change 3 — OB/FVG proximity tolerance (optional, smaller impact)

**File:** `app/analysis/pro/conditions.py`

Extend OB/FVG zone from exact touch to within 0.3% of zone (price approaching POI, not only inside it).

**Why:** 80% Order Block failure — price near but outside zone.

---

## Expected outcome after Change 1 + 2

- BOS/Liquidity pass rate should rise from 0–20% to 40–60% on trending periods
- EMA/HTF proxy pass rate should rise when structure is directional
- Confluence scores should reach 40–70 range during active sessions
- Signals resume **without changing confidence thresholds**

---

## What NOT to do

- Do not blindly lower `TELEGRAM_NOTIFY_MIN_CONFIDENCE` from 90 — engine never reaches 65 today
- Do not reduce `PRO_MIN_CONDITIONS` until persistence fix is validated on VPS logs

---

## Next step

1. Fix SSH → deploy with `./scripts/deploy/contabo_deploy.sh`
2. Run `bash scripts/vps_collect_diagnostics.sh` after 2–4 hours
3. Implement **Change 1** (structure persistence) as the minimal PR
