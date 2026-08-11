# Signal Pipeline Diagnostic Report

- Engine: **v1**
- Symbols scanned: **5**
- Engine signals (BUY/SELL): **0**
- Telegram-eligible: **0**
- Blocked by Telegram confidence gate: **0**

## Failure Frequency (checks that failed)

- **BOS**: 4/5 scans (80%)
- **CHOCH**: 4/5 scans (80%)
- **FVG**: 3/5 scans (60%)
- **Regime**: 3/5 scans (60%)
- **EMA**: 3/5 scans (60%)
- **HTF**: 2/5 scans (40%)
- **Order Block**: 1/5 scans (20%)
- **RSI**: 1/5 scans (20%)
- **Liquidity**: 1/5 scans (20%)
- **ADX**: 1/5 scans (20%)

## Per-Symbol Results

```
BTCUSDT
Market regime: Strong Trend
HTF bias: PASS (HTF BEARISH, LTF BEARISH)
Market structure: DOWNTREND
BOS: FAIL (No bearish BOS (NO_BOS))
CHOCH: PASS (BEARISH_CHOCH)
Liquidity sweep: PASS (Buy-side sweep at 67136.75)
Order Block: FAIL (Order block present but price outside 0.3% proximity)
FVG: FAIL (Active BEARISH FVG outside 0.3% proximity)
EMA filter: PASS (Bearish EMA trend)
ADX: PASS (ADX 53.1 (min 24))
ATR: PASS (Tradeable volatility (0.45% ATR))
RSI: FAIL (RSI 11.6 outside bearish zone 32–55)
Regime gate: FAIL (Strong Trend requires BOS)
Confidence score: 46.0
Final decision: WAIT
Rejection reason: Rejected because BOS failed | Engine: Confluence insufficient (best score 46.0, need 5 factors and 65 confidence) | Failed: BOS, Order Block, FVG, RSI
```

```
ETHUSDT
Market regime: Weak Trend + Low Volatility
HTF bias: FAIL (HTF BULLISH, LTF BEARISH — no bearish HTF alignment)
Market structure: DOWNTREND
BOS: FAIL (No bearish BOS (NO_BOS))
CHOCH: FAIL (No bearish CHOCH (NO_CHOCH))
Liquidity sweep: PASS (Buy-side sweep at 1921.88)
Order Block: PASS (Bearish OB 1924.15–1924.93)
FVG: PASS (Bearish FVG 1923.19–1923.94)
EMA filter: FAIL (Trend=BEARISH, close vs EMA50 misaligned)
ADX: PASS (ADX 26.1 (min 24))
ATR: PASS (Tradeable volatility (0.15% ATR))
RSI: PASS (RSI 47.8)
Regime gate: FAIL (Weak Trend requires BOS or CHOCH)
Confidence score: 29.5
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Confluence insufficient (best score 29.5, need 5 factors and 65 confidence) | Failed: HTF, BOS, CHOCH, EMA
```

```
SOLUSDT
Market regime: Weak Trend + High Volatility
HTF bias: FAIL (HTF BEARISH, LTF SIDEWAYS — no bullish HTF alignment)
Market structure: RANGE
BOS: FAIL (No bullish BOS (NO_BOS))
CHOCH: FAIL (No bullish CHOCH (NO_CHOCH))
Liquidity sweep: PASS (Sell-side sweep at 76.99)
Order Block: PASS (Bullish OB 76.90–77.05)
FVG: FAIL (No active FVG)
EMA filter: FAIL (Trend=SIDEWAYS, close vs EMA50 misaligned)
ADX: PASS (ADX 79.3 (min 24))
ATR: PASS (Tradeable volatility (6.65% ATR))
RSI: PASS (RSI 52.6)
Regime gate: FAIL (Weak Trend requires BOS or CHOCH)
Confidence score: 29.5
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Confluence insufficient (best score 29.5, need 5 factors and 65 confidence) | Failed: HTF, BOS, CHOCH, FVG
```

```
XRPUSDT
Market regime: Weak Trend
HTF bias: PASS (HTF BULLISH, LTF SIDEWAYS)
Market structure: RANGE
BOS: PASS (BULLISH_BOS)
CHOCH: FAIL (No bullish CHOCH (NO_CHOCH))
Liquidity sweep: FAIL (Sweep type BUY_SIDE_SWEEP not aligned for BUY)
Order Block: PASS (Bullish OB 1.11–1.12)
FVG: FAIL (No active FVG)
EMA filter: FAIL (Trend=SIDEWAYS, close vs EMA50 misaligned)
ADX: PASS (ADX 27.3 (min 24))
ATR: PASS (Tradeable volatility (1.44% ATR))
RSI: PASS (RSI 48.4)
Regime gate: PASS (Weak Trend confirmations satisfied)
Confidence score: 35.1
Final decision: WAIT
Rejection reason: Rejected because CHOCH failed | Engine: Confluence insufficient (best score 35.1, need 5 factors and 65 confidence) | Failed: CHOCH, Liquidity, FVG, EMA
```

```
DOGEUSDT
Market regime: Range + Low Volatility
HTF bias: PASS (HTF SIDEWAYS, LTF BEARISH)
Market structure: DOWNTREND
BOS: FAIL (No bearish BOS (NO_BOS))
CHOCH: FAIL (No bearish CHOCH (NO_CHOCH))
Liquidity sweep: PASS (Buy-side sweep at 0.07)
Order Block: PASS (Bearish OB 0.07–0.07)
FVG: PASS (Bearish FVG 0.07–0.07)
EMA filter: PASS (Bearish EMA trend)
ADX: FAIL (ADX 11.1 (min 24))
ATR: PASS (Tradeable volatility (0.25% ATR))
RSI: PASS (RSI 49.8)
Regime gate: PASS (Range confirmations satisfied (ADX not required in low volatility))
Confidence score: 46.8
Final decision: WAIT
Rejection reason: Rejected because BOS failed | Engine: Confluence insufficient (best score 46.8, need 5 factors and 65 confidence) | Failed: BOS, CHOCH, ADX
```


## Analysis

Primary blocker across scans: **BOS** failed in 4/5 scans (80%).
PRO v1 requires **5** aligned conditions, **65** confidence, and **10** direction gap — all must pass simultaneously.
Best candidate confidence this scan: **46.8**. Engine threshold is 65; Telegram requires 80.

### Recommended fixes (do not lower confidence blindly)

1. **Run this diagnostic on the VPS** after deploy — logs every scan cycle automatically.
2. **Align Telegram gate with engine output** — if engine max confidence is 65–85, set `TELEGRAM_NOTIFY_MIN_CONFIDENCE` to match engine grade mapping, not 90.
3. **If Liquidity is top blocker** — consider requiring liquidity OR structure break (not both) for v1 confluence, or widen sweep lookback in a future engine change.
4. **If using v2** — enable shadow mode: log v2 diagnostics while trading v1 until narrative completion rate is validated on live data.
5. **Verify closed-bar timing** — scanners on forming bars may miss sweeps that complete on bar close; confirm `MarketContextBuilder` uses closed bars only.