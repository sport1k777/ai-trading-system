# PRO V2 Zero-Signal Root Cause Report

Generated from walk-forward replay (`SIGNAL_ENGINE_VERSION=v2`, 672 bars/symbol).
**No strategy changes deployed.**

## Production verification (7 days live logs)

Source: `journalctl -u ai-trading-signals` on VPS, ~22,789 gate audits.

| Metric | Value |
|--------|-------|
| Engine BUY/SELL | **0** (100% WAIT) |
| Telegram alerts sent | **0** |
| Narrative gate (diagnostic) | **100% PASS** ← misleading |
| Grade gate pass | **165 / 22,789 (0.7%)** |
| Liquidity gate pass | **94.4%** (rarely blocks) |

**Production gate fail rates (setup filters):**

| Filter | Fail rate |
|--------|-----------|
| FVG | 73.0% |
| CHOCH | 69.9% |
| Confirmations (diagnostic) | 68.8% |
| BOS | 55.5% |
| Regime gates | 52.5% |
| EMA | 45.6% |
| RSI | 41.0% |
| HTF | 28.7% |
| ADX | 22.1% |
| Order Block | 16.6% |
| ATR | 16.5% |
| Liquidity | 5.6% |

**Top engine exit reasons (production):**

1. Regime: Structure Alignment blocks direction — **3,859 scans**
2. Setup incomplete: missing **Displacement** — dominates missing-step list
3. Setup incomplete: missing **Structure Break / Confirmation**
4. Regime: ADX below 22

**Per-symbol top blocker (production):**

| Symbol | Primary blocker |
|--------|-----------------|
| BTCUSDT | Structure blocks long + incomplete SHORT (Displacement) |
| ETHUSDT | Structure blocks long + incomplete LONG (Displacement) |
| SOLUSDT | Structure blocks long + incomplete LONG (Displacement) |
| XRPUSDT | HTF Bias + Displacement on both directions |
| DOGEUSDT | Structure blocks long + Displacement on LONG |

**Live vs replay gap:** Bar-close replay found **5** engine BUY/SELL (BTC×1, XRP×4) over 7 days, but production had **0**. The service scans every **60s** at arbitrary candle snapshots — the 7-step narrative aligns on only **~1.3%** of bar closes and those windows are easy to miss between scans.

## Aggregate

- Total scans: **3360**
- Engine BUY/SELL: **5**
- Complete narratives: **43**

**Top blockers (all symbols):**

- Regime: ADX Trend: 26.0%
- Regime: ATR Volatility: 15.8%
- Setup incomplete: Displacement: 15.4%
- Setup incomplete: HTF Bias: 15.1%
- Regime: Structure Alignment: 14.2%
- Setup incomplete: Premium/Discount: 8.6%
- Setup incomplete: Liquidity Sweep: 1.8%
- Setup incomplete: Confirmation: 1.4%
- Setup incomplete: Structure Break: 1.0%
- Risk: levels unavailable: 0.3%
- Setup incomplete: POI Return: 0.1%
- ATR Volatility: 0.1%

## Per-symbol breakdown

### BTCUSDT

- Scans: **672** | Engine BUY/SELL: **1** | Complete narratives: **11** (1.6%)
- Counterfactual (complete + risk OK + grade B): **0** scans

**Primary blockers (first engine exit):**

- Regime: ADX Trend: 172/672 (25.6%)
- Regime: ATR Volatility: 122/672 (18.2%)
- Setup incomplete: HTF Bias: 112/672 (16.7%)
- Regime: Structure Alignment: 102/672 (15.2%)
- Setup incomplete: Displacement: 70/672 (10.4%)
- Setup incomplete: Premium/Discount: 58/672 (8.6%)
- Setup incomplete: Confirmation: 19/672 (2.8%)
- Setup incomplete: Structure Break: 9/672 (1.3%)

**Regime gates (% pass):**

- ATR Volatility: 81.8%
- ADX Trend: 64.0%
- Structure Alignment: 76.3%
- Session: 100.0%

**Sequential steps (% pass on best narrative):**

- HTF Bias: 69.5%
- Premium/Discount: 63.9%
- Liquidity Sweep: 95.2%
- Displacement: 31.0%
- POI Return: 94.2%
- Structure Break: 74.6%
- Confirmation: 14.9%
- CHOCH: 100.0%

**Confirmations (% aligned):**

- EMA Stack: 58.3%
- RSI: 54.2%
- VWAP: 57.1%
- Volume Profile: 74.4%

**Dominant blocker type:** strict_threshold

### ETHUSDT

- Scans: **672** | Engine BUY/SELL: **0** | Complete narratives: **6** (0.9%)
- Counterfactual (complete + risk OK + grade B): **0** scans

**Primary blockers (first engine exit):**

- Regime: ADX Trend: 243/672 (36.2%)
- Setup incomplete: Displacement: 136/672 (20.2%)
- Regime: Structure Alignment: 107/672 (15.9%)
- Setup incomplete: Premium/Discount: 103/672 (15.3%)
- Setup incomplete: HTF Bias: 42/672 (6.2%)
- Setup incomplete: Liquidity Sweep: 14/672 (2.1%)
- Setup incomplete: Confirmation: 12/672 (1.8%)
- Regime: ATR Volatility: 8/672 (1.2%)

**Regime gates (% pass):**

- ATR Volatility: 98.8%
- ADX Trend: 63.5%
- Structure Alignment: 77.2%
- Session: 100.0%

**Sequential steps (% pass on best narrative):**

- HTF Bias: 80.0%
- Premium/Discount: 62.1%
- Liquidity Sweep: 94.0%
- Displacement: 27.1%
- POI Return: 91.1%
- Structure Break: 60.3%
- Confirmation: 20.2%
- CHOCH: 100.0%

**Confirmations (% aligned):**

- EMA Stack: 47.5%
- RSI: 59.2%
- VWAP: 59.2%
- Volume Profile: 63.4%

**Dominant blocker type:** strict_threshold

### SOLUSDT

- Scans: **672** | Engine BUY/SELL: **0** | Complete narratives: **2** (0.3%)
- Counterfactual (complete + risk OK + grade B): **0** scans

**Primary blockers (first engine exit):**

- Regime: ATR Volatility: 400/672 (59.5%)
- Setup incomplete: HTF Bias: 74/672 (11.0%)
- Setup incomplete: Displacement: 71/672 (10.6%)
- Regime: ADX Trend: 63/672 (9.4%)
- Regime: Structure Alignment: 42/672 (6.2%)
- Setup incomplete: Premium/Discount: 11/672 (1.6%)
- Setup incomplete: Liquidity Sweep: 10/672 (1.5%)
- Grade gate (need ≥A, got B): 1/672 (0.1%)

**Regime gates (% pass):**

- ATR Volatility: 40.5%
- ADX Trend: 90.6%
- Structure Alignment: 81.0%
- Session: 100.0%

**Sequential steps (% pass on best narrative):**

- HTF Bias: 48.5%
- Premium/Discount: 86.3%
- Liquidity Sweep: 93.9%
- Displacement: 1.9%
- POI Return: 94.2%
- Structure Break: 44.0%
- Confirmation: 26.2%
- CHOCH: 100.0%

**Confirmations (% aligned):**

- EMA Stack: 59.7%
- RSI: 68.9%
- VWAP: 33.6%
- Volume Profile: 42.9%

**Dominant blocker type:** strict_threshold

### XRPUSDT

- Scans: **672** | Engine BUY/SELL: **4** | Complete narratives: **12** (1.8%)
- Counterfactual (complete + risk OK + grade B): **0** scans

**Primary blockers (first engine exit):**

- Setup incomplete: HTF Bias: 183/672 (27.2%)
- Regime: ADX Trend: 179/672 (26.6%)
- Regime: Structure Alignment: 109/672 (16.2%)
- Setup incomplete: Displacement: 89/672 (13.2%)
- Setup incomplete: Premium/Discount: 75/672 (11.2%)
- Setup incomplete: Liquidity Sweep: 18/672 (2.7%)
- Setup incomplete: Structure Break: 7/672 (1.0%)
- ATR Volatility: 4/672 (0.6%)

**Regime gates (% pass):**

- ATR Volatility: 100.0%
- ADX Trend: 73.4%
- Structure Alignment: 78.9%
- Session: 100.0%

**Sequential steps (% pass on best narrative):**

- HTF Bias: 60.9%
- Premium/Discount: 75.8%
- Liquidity Sweep: 94.5%
- Displacement: 15.0%
- POI Return: 93.9%
- Structure Break: 56.1%
- Confirmation: 28.9%
- CHOCH: 100.0%

**Confirmations (% aligned):**

- EMA Stack: 39.0%
- RSI: 69.6%
- VWAP: 58.3%
- Volume Profile: 77.8%

**Dominant blocker type:** strict_threshold

### DOGEUSDT

- Scans: **672** | Engine BUY/SELL: **0** | Complete narratives: **12** (1.8%)
- Counterfactual (complete + risk OK + grade B): **0** scans

**Primary blockers (first engine exit):**

- Regime: ADX Trend: 217/672 (32.3%)
- Setup incomplete: Displacement: 153/672 (22.8%)
- Regime: Structure Alignment: 116/672 (17.3%)
- Setup incomplete: HTF Bias: 95/672 (14.1%)
- Setup incomplete: Premium/Discount: 41/672 (6.1%)
- Setup incomplete: Liquidity Sweep: 16/672 (2.4%)
- Setup incomplete: Confirmation: 13/672 (1.9%)
- Setup incomplete: Structure Break: 11/672 (1.6%)

**Regime gates (% pass):**

- ATR Volatility: 100.0%
- ADX Trend: 67.7%
- Structure Alignment: 77.4%
- Session: 100.0%

**Sequential steps (% pass on best narrative):**

- HTF Bias: 57.4%
- Premium/Discount: 87.2%
- Liquidity Sweep: 93.5%
- Displacement: 13.7%
- POI Return: 97.8%
- Structure Break: 53.8%
- Confirmation: 29.3%
- CHOCH: 100.0%

**Confirmations (% aligned):**

- EMA Stack: 40.6%
- RSI: 65.6%
- VWAP: 61.9%
- Volume Profile: 82.4%

**Dominant blocker type:** strict_threshold

## Root cause summary

Across **3360** walk-forward scans (7 days × 5 symbols, PRO v2):
- Engine BUY/SELL emitted: **5**
- Complete sequential narratives: **43** (1.3%)
- Would emit at grade B (counterfactual): **0**

**Top primary blockers:**

- Regime: ADX Trend: 26.0%
- Regime: ATR Volatility: 15.8%
- Setup incomplete: Displacement: 15.4%
- Setup incomplete: HTF Bias: 15.1%
- Regime: Structure Alignment: 14.2%
- Setup incomplete: Premium/Discount: 8.6%
- Setup incomplete: Liquidity Sweep: 1.8%
- Setup incomplete: Confirmation: 1.4%
- Setup incomplete: Structure Break: 1.0%
- Risk: levels unavailable: 0.3%

**Most often missing sequential step (when incomplete):**

- HTF Bias: 1224 scans
- Displacement: 1127 scans
- Premium/Discount: 640 scans
- Liquidity Sweep: 152 scans
- Confirmation: 92 scans
- Structure Break: 74 scans
- POI Return: 8 scans

## Logic bugs vs strict thresholds

| Issue | Type | Evidence |
|-------|------|----------|
| Regime ADX always uses trend threshold (≥22); reversal ADX mode never called | **Logic bug** | `run_regime_gates()` never passes `for_trend_setup=False` |
| Diagnostic treats all 4 confirmations as hard gate; engine only needs 2 for grade A | **Logic bug** | Mismatch causes misleading production logs |
| Diagnostic Narrative gate passes when direction set, even if incomplete | **Logic bug** | `_build_engine_gate_checks_v2` checks `direction is not None` |
| Engine `_wait()` sets confidence=0 unless grade path reached | **Logic bug** | Masks near-miss confidence in logs/Telegram gate |
| POI Return requires price within 0.3% of OB/FVG | **Strict threshold** | Step fails ~60–80% of scans |
| Continuation requires 6/7 steps + premium/discount simultaneously | **Strict threshold** | Complete narrative rate near zero |
| Grade A requires 2 confirmations + HTF strength ≥70 | **Strict threshold** | Only 165/22,789 scans pass grade gate in production |
| Confirmation candle requires volume_ratio ≥1.0 on signal bar | **Strict threshold** | Fails on low-volume closes |
| Displacement requires 1.3×ATR body in last 5 bars | **Strict threshold** | Often missing in low-vol regimes |

## Minimum recommended changes (do not deploy yet)

These preserve quality while fixing bugs and unlocking realistic signal rate (~1–3/day):

1. **Fix ADX regime routing** — use `for_trend_setup=False` when best narrative is reversal; avoids blocking valid reversal setups with trend ADX.
2. **Fix diagnostic v2 gates** — audit Narrative/Confirmations to match engine (track sequential steps individually; confirmations = count ≥2, not all 4).
3. **Pass computed confidence in `_wait()`** when grade was computed — improves observability only, no strategy change.
4. **Align POI proximity with regime profile** — use existing `REGIME_POI_TOLERANCE_*` in `_poi_return()` instead of fixed 0.3%; same adaptive logic already used in v1 diagnostics.
5. **Relax confirmation candle volume** — `volume_ratio >= 0.85` OR remove volume requirement when 5+ narrative steps complete; reduces false negatives without skipping the sequence.
6. **Only if counterfactual grade-B count > 0 after fixes** — set `PRO_V2_MIN_GRADE=B` (not lower). Grade B still requires step_hits ≥ n-2 and ≥1 confirmation.

**Do not change:** R:R ≥2.0, sequential narrative requirement, HTF bias step, or Telegram confidence gate without re-auditing.

