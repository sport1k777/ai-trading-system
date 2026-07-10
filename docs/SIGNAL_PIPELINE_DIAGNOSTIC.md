# Signal Pipeline Diagnostic Report

- Engine: **v1**
- Symbols scanned: **5**
- Engine signals (BUY/SELL): **0**
- Telegram-eligible: **0**
- Blocked by Telegram confidence gate: **0**

## Failure Frequency (checks that failed)

- **Order Block**: 4/5 scans (80%)
- **FVG**: 4/5 scans (80%)
- **BOS**: 3/5 scans (60%)
- **CHOCH**: 3/5 scans (60%)
- **RSI**: 3/5 scans (60%)
- **HTF**: 2/5 scans (40%)
- **EMA**: 2/5 scans (40%)
- **ADX**: 2/5 scans (40%)
- **ATR**: 1/5 scans (20%)

## Per-Symbol Results

```
BTCUSDT
HTF bias: PASS (LTF trend BEARISH)
Market structure: DOWNTREND
BOS: FAIL (No bearish BOS (NO_BOS))
CHOCH: FAIL (No bearish CHOCH (NO_CHOCH))
Liquidity sweep: PASS (Price below buy-side pool 64409.38)
Order Block: FAIL (Order block present but price outside 0.3% proximity)
FVG: FAIL (Active BEARISH FVG outside 0.3% proximity)
EMA filter: PASS (Bearish EMA trend)
ADX: PASS (ADX 62.4 (min 24))
ATR: PASS (Tradeable volatility (0.19% ATR))
RSI: PASS (RSI 35.1)
Confidence score: 22.0
Final decision: WAIT
Rejection reason: Rejected because BOS failed | Engine: Confluence insufficient (best score 22.0, need 5 factors and 65 confidence) | Failed: BOS, CHOCH, Order Block, FVG
```

```
ETHUSDT
HTF bias: PASS (LTF trend BULLISH)
Market structure: UPTREND
BOS: PASS (BULLISH_BOS)
CHOCH: PASS (BULLISH_CHOCH)
Liquidity sweep: PASS (Price above sell-side pool 1784.89)
Order Block: FAIL (Order block present but price outside 0.3% proximity)
FVG: FAIL (Active BULLISH FVG outside 0.3% proximity)
EMA filter: PASS (Bullish EMA trend)
ADX: PASS (ADX 72.3 (min 24))
ATR: PASS (Tradeable volatility (0.57% ATR))
RSI: FAIL (RSI 89.0 outside bullish zone 45–68)
Confidence score: 39.0
Final decision: WAIT
Rejection reason: Rejected because Order Block failed | Engine: Confluence insufficient (best score 39.0, need 5 factors and 65 confidence) | Failed: Order Block, FVG, RSI
```

```
SOLUSDT
HTF bias: FAIL (LTF trend BEARISH — no bullish HTF proxy)
Market structure: DOWNTREND
BOS: FAIL (No bullish BOS (BEARISH_BOS))
CHOCH: FAIL (No bullish CHOCH (BEARISH_CHOCH))
Liquidity sweep: PASS (Price above sell-side pool 77.61)
Order Block: FAIL (Order block present but price outside 0.3% proximity)
FVG: FAIL (Active BEARISH FVG outside 0.3% proximity)
EMA filter: FAIL (Trend=BEARISH, close vs EMA50 misaligned)
ADX: PASS (ADX 94.4 (min 24))
ATR: FAIL (Volatility out of tradeable range (5.99% ATR))
RSI: FAIL (RSI 35.6 outside bullish zone 45–68)
Confidence score: 0.0
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Volatility out of tradeable range (5.99% ATR) | Failed: HTF, BOS, CHOCH, Order Block
```

```
XRPUSDT
HTF bias: FAIL (LTF trend SIDEWAYS — no bearish HTF proxy)
Market structure: RANGE
BOS: PASS (BEARISH_BOS)
CHOCH: PASS (BEARISH_CHOCH)
Liquidity sweep: PASS (Buy-side sweep at 1.16)
Order Block: FAIL (Order block present but price outside 0.3% proximity)
FVG: FAIL (No active FVG)
EMA filter: FAIL (Trend=SIDEWAYS, close vs EMA50 misaligned)
ADX: FAIL (ADX 20.2 (min 24))
ATR: PASS (Tradeable volatility (1.94% ATR))
RSI: FAIL (RSI 56.6 outside bearish zone 32–55)
Confidence score: 30.0
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Confluence insufficient (best score 30.0, need 5 factors and 65 confidence) | Failed: HTF, Order Block, FVG, EMA
```

```
DOGEUSDT
HTF bias: PASS (LTF trend BULLISH)
Market structure: UPTREND
BOS: FAIL (No bullish BOS (NO_BOS))
CHOCH: FAIL (No bullish CHOCH (NO_CHOCH))
Liquidity sweep: PASS (Price above sell-side pool 0.07)
Order Block: PASS (Bullish OB 0.07–0.07)
FVG: PASS (Bullish FVG 0.07–0.07)
EMA filter: PASS (Bullish EMA trend)
ADX: FAIL (ADX 11.5 (min 24))
ATR: PASS (Tradeable volatility (0.36% ATR))
RSI: PASS (RSI 48.9)
Confidence score: 46.0
Final decision: WAIT
Rejection reason: Rejected because BOS failed | Engine: Confluence insufficient (best score 46.0, need 5 factors and 65 confidence) | Failed: BOS, CHOCH, ADX
```


## Analysis

Primary blocker across scans: **Order Block** failed in 4/5 scans (80%).
PRO v1 requires **5** aligned conditions, **65** confidence, and **10** direction gap — all must pass simultaneously.
Price must be **within 0.3%** of an active FVG or order block zone. Wider proximity helps, but confluence may still fall short of 5 factors.
Best candidate confidence this scan: **46.0**. Engine threshold is 65; Telegram requires 90.

### Recommended fixes (do not lower confidence blindly)

1. **Run this diagnostic on the VPS** after deploy — logs every scan cycle automatically.
2. **Align Telegram gate with engine output** — if engine max confidence is 65–85, set `TELEGRAM_NOTIFY_MIN_CONFIDENCE` to match engine grade mapping, not 90.
3. **If Liquidity is top blocker** — consider requiring liquidity OR structure break (not both) for v1 confluence, or widen sweep lookback in a future engine change.
4. **If using v2** — enable shadow mode: log v2 diagnostics while trading v1 until narrative completion rate is validated on live data.
5. **Verify closed-bar timing** — scanners on forming bars may miss sweeps that complete on bar close; confirm `MarketContextBuilder` uses closed bars only.