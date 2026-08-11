# Signal Pipeline — Mathematical Proof & Live Evidence

**Captured:** 2026-07-16 09:04 UTC (live Bybit 15m scan)

## Historical replay (1000 bars × 5 symbols, post-fix)

| Metric | Count |
|--------|-------|
| Engine signals (≥65 conf + regime) | **4** |
| Telegram eligible (≥80 conf) | **1** |
| Global peak confidence | **81.2%** (SOLUSDT) |

**Telegram-eligible trade (proven):**

```
SOLUSDT | 2026-07-13 09:45 UTC | BUY | confidence 81.2%
Regime: Strong Trend + High Volatility
HTF: PASS | BOS: PASS | CHOCH: PASS | Liquidity: PASS
Order Block: PASS | FVG: PASS | EMA: PASS | ADX: PASS | RSI: PASS
Regime gate: PASS
Final decision: ALERT BUY
```

**End-to-end Telegram delivery:** replayed through `TradingPipeline` → `format_live_signal_message` → `TelegramNotifier.send_message` → **SUCCESS** (after MarkdownV2 `81.2%` escape fix).

## Live scan NOW (2026-07-16 ~09:04 UTC)

| Symbol | Conf | Decision | Primary rejection |
|--------|------|----------|-----------------|
| BTCUSDT | 46.0 | WAIT | BOS failed; 4/5 hits; need 65 |
| ETHUSDT | 29.5 | WAIT | HTF/BOS/CHOCH; 2 hits |
| SOLUSDT | 29.5 | WAIT | HTF/BOS/CHOCH; 2 hits |
| XRPUSDT | 35.1 | WAIT | CHOCH/Liquidity; 4 hits |
| DOGEUSDT | 46.8 | WAIT | BOS/CHOCH; 2 hits |

**Engine signals now: 0/5** — current market lacks simultaneous BOS + 5-factor confluence at 65+.

| Symbol | Regime | Best side | Confidence | Hits | Engine | Rejection |
|--------|--------|-----------|------------|------|--------|-----------|
| BTCUSDT | Strong Trend | SELL | **36.0** | 4/5 | WAIT | BOS missing; need 65 conf |
| ETHUSDT | Weak Trend + Low Vol | SELL | **19.6** | 2/5 | WAIT | BOS/CHOCH; HTF misaligned |
| SOLUSDT | Weak Trend + High Vol | BUY | **17.9** | 2/5 | WAIT | BOS/CHOCH; HTF bearish |
| XRPUSDT | Weak Trend | BUY | **35.1** | 4/5 | WAIT | Regime OK; need 5 hits + 65 conf |
| DOGEUSDT | Range + Low Vol | SELL | **20.0** | 2/5 | WAIT | Regime gate; BOS/CHOCH |

**Engine signals (BUY/SELL): 0/5**  
**Telegram-eligible @90: 0/5** (impossible — see below)

## Why Telegram @90 never fired (mathematical proof)

Confluence confidence = `(sum of aligned directional weights) / 122 × 100`

Maximum directional weight sum (all 9 factors aligned):

| Factor | Weight |
|--------|--------|
| BOS + CHOCH | 15.0 |
| FVG | 12.0 |
| Order Block | 12.0 |
| Liquidity | 15.0 |
| EMA | 12.0 |
| ADX | 10.0 |
| HTF | 12.0 |
| RSI | 10.0 |
| **Total** | **98.0** |

**Max achievable confidence = 98 / 122 = 80.3%**

With strong-trend weight boost: **104 / 122 = 85.2%**

| Gate | Required weight sum | Achievable? |
|------|---------------------|-------------|
| Engine (`PRO_MIN_CONFIDENCE=65`) | 79.3 | Yes (needs ~6–7 aligned factors) |
| Telegram @90 | 109.8 | **NO — exceeds max possible (112% of ceiling)** |
| Telegram @80 (Grade A) | 97.6 | Yes — matches highest tier |

**Conclusion:** `TELEGRAM_NOTIFY_MIN_CONFIDENCE=90` made Telegram alerts **impossible by design**.  
Fixed default: **80** (Grade A — highest score the engine can produce).

## Historical evidence (BTCUSDT, 1000 × 15m bars)

Sampled every 8 bars after warmup:

- **Peak confidence: 64.2%** (0.8 below engine threshold 65)
- **Engine emits: 0**
- **Telegram @90: 0**

## Bugs found (engine vs diagnostic mismatch)

1. **Liquidity:** Diagnostic used pool proximity (`liquidity_swept_recently`); engine used bar sweep only → diagnostic PASS, confluence FAIL. **Fixed:** `LiquidityAnalyzer.resolve()`.

2. **ADX/EMA with SIDEWAYS trend:** ADX confirmed strength but scored NEUTRAL when `trend=SIDEWAYS` despite `structure=UPTREND/DOWNTREND`. **Fixed:** use structure as effective trend.

3. **Telegram gate @90:** Mathematically unreachable. **Fixed:** default **80**.

## Per-scan log format (production)

Every cycle logs at INFO via `signal_service._log_scan_diagnostic()`:

```
BTCUSDT
Market regime: Strong Trend
HTF bias: PASS/FAIL (...)
BOS: PASS/FAIL (...)
CHOCH: PASS/FAIL (...)
Liquidity sweep: PASS/FAIL (...)
Order Block: PASS/FAIL (...)
FVG: PASS/FAIL (...)
EMA filter: PASS/FAIL (...)
ADX: PASS/FAIL (...)
ATR: PASS/FAIL (...)
RSI: PASS/FAIL (...)
Regime gate: PASS/FAIL (...)
Confidence score: XX.X
Final decision: WAIT | ALERT BUY | BLOCKED (...)
Rejection reason: Rejected because ... 
```

No silent rejections.

## Commands to reproduce

```bash
# Live one-shot diagnostic
PYTHONPATH=. python scripts/signal_pipeline_diagnostic.py

# Per-symbol confluence math
PYTHONPATH=. python scripts/validate_production.py
```
