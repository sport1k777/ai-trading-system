# Signal Pipeline Diagnostic Report

- Engine: **v1**
- Symbols scanned: **5**
- Engine signals (BUY/SELL): **0**
- Telegram-eligible: **0**
- Blocked by Telegram confidence gate: **0**

## Failure Frequency (checks that failed)

- **HTF**: 5/5 scans (100%)
- **BOS**: 5/5 scans (100%)
- **CHOCH**: 5/5 scans (100%)
- **EMA**: 5/5 scans (100%)
- **Order Block**: 4/5 scans (80%)
- **FVG**: 3/5 scans (60%)
- **RSI**: 2/5 scans (40%)
- **ADX**: 2/5 scans (40%)
- **ATR**: 1/5 scans (20%)
- **Liquidity**: 1/5 scans (20%)

## Per-Symbol Results

```
BTCUSDT
HTF bias: FAIL (LTF trend SIDEWAYS — no bearish HTF proxy)
Market structure: DOWNTREND
BOS: FAIL (No bearish BOS (NO_BOS))
CHOCH: FAIL (No bearish CHOCH (NO_CHOCH))
Liquidity sweep: PASS (Price below buy-side pool 64408.26)
Order Block: FAIL (Order block present but price outside aligned zone)
FVG: PASS (Bearish FVG 64240.60–64395.20)
EMA filter: FAIL (Trend=SIDEWAYS, close vs EMA50 misaligned)
ADX: PASS (ADX 63.4 (min 24))
ATR: PASS (Tradeable volatility (0.18% ATR))
RSI: PASS (RSI 36.7)
Confidence score: 22.0
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Confluence insufficient (best score 22.0, need 5 factors and 65 confidence) | Failed: HTF, BOS, CHOCH, Order Block
```

```
ETHUSDT
HTF bias: FAIL (LTF trend SIDEWAYS — no bullish HTF proxy)
Market structure: UPTREND
BOS: FAIL (No bullish BOS (NO_BOS))
CHOCH: FAIL (No bullish CHOCH (NO_CHOCH))
Liquidity sweep: PASS (Price above sell-side pool 1783.86)
Order Block: FAIL (Order block present but price outside aligned zone)
FVG: PASS (Bullish FVG 1783.94–1785.94)
EMA filter: FAIL (Trend=SIDEWAYS, close vs EMA50 misaligned)
ADX: PASS (ADX 71.2 (min 24))
ATR: PASS (Tradeable volatility (0.47% ATR))
RSI: FAIL (RSI 73.1 outside bullish zone 45–68)
Confidence score: 12.0
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Confluence insufficient (best score 12.0, need 5 factors and 65 confidence) | Failed: HTF, BOS, CHOCH, Order Block
```

```
SOLUSDT
HTF bias: FAIL (LTF trend SIDEWAYS — no bullish HTF proxy)
Market structure: DOWNTREND
BOS: FAIL (No bullish BOS (NO_BOS))
CHOCH: FAIL (No bullish CHOCH (BEARISH_CHOCH))
Liquidity sweep: PASS (Price above sell-side pool 77.61)
Order Block: FAIL (Order block present but price outside aligned zone)
FVG: FAIL (Active BEARISH FVG not engaged)
EMA filter: FAIL (Trend=SIDEWAYS, close vs EMA50 misaligned)
ADX: PASS (ADX 94.5 (min 24))
ATR: FAIL (Volatility out of tradeable range (6.39% ATR))
RSI: FAIL (RSI 41.9 outside bullish zone 45–68)
Confidence score: 0.0
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Volatility out of tradeable range (6.39% ATR) | Failed: HTF, BOS, CHOCH, Order Block
```

```
XRPUSDT
HTF bias: FAIL (LTF trend SIDEWAYS — no bullish HTF proxy)
Market structure: RANGE
BOS: FAIL (No bullish BOS (NO_BOS))
CHOCH: FAIL (No bullish CHOCH (NO_CHOCH))
Liquidity sweep: PASS (Price above sell-side pool 1.10)
Order Block: FAIL (Order block present but price outside aligned zone)
FVG: FAIL (No active FVG)
EMA filter: FAIL (Trend=SIDEWAYS, close vs EMA50 misaligned)
ADX: FAIL (ADX 20.3 (min 24))
ATR: PASS (Tradeable volatility (1.73% ATR))
RSI: PASS (RSI 48.1)
Confidence score: 10.0
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Confluence insufficient (best score 10.0, need 5 factors and 65 confidence) | Failed: HTF, BOS, CHOCH, Order Block
```

```
DOGEUSDT
HTF bias: FAIL (LTF trend SIDEWAYS — no bearish HTF proxy)
Market structure: UPTREND
BOS: FAIL (No bearish BOS (NO_BOS))
CHOCH: FAIL (No bearish CHOCH (NO_CHOCH))
Liquidity sweep: FAIL (No liquidity sweep detected)
Order Block: PASS (Bearish OB 0.07–0.07)
FVG: FAIL (Active BULLISH FVG not engaged)
EMA filter: FAIL (Trend=SIDEWAYS, close vs EMA50 misaligned)
ADX: FAIL (ADX 12.4 (min 24))
ATR: PASS (Tradeable volatility (0.35% ATR))
RSI: PASS (RSI 54.4)
Confidence score: 12.0
Final decision: WAIT
Rejection reason: Rejected because HTF failed | Engine: Confluence insufficient (best score 12.0, need 5 factors and 65 confidence) | Failed: HTF, BOS, CHOCH, Liquidity
```


## Analysis

Primary blocker across scans: **HTF** failed in 5/5 scans (100%).
PRO v1 requires **5** aligned conditions, **65** confidence, and **10** direction gap — all must pass simultaneously.
Price must be **inside** an active FVG or order block zone. Most of the time price trades outside these zones, so confluence rarely reaches 5 factors.
Best candidate confidence this scan: **22.0**. Engine threshold is 65; Telegram requires 90.

### Recommended fixes (do not lower confidence blindly)

1. **Run this diagnostic on the VPS** after deploy — logs every scan cycle automatically.
2. **Align Telegram gate with engine output** — if engine max confidence is 65–85, set `TELEGRAM_NOTIFY_MIN_CONFIDENCE` to match engine grade mapping, not 90.
3. **If Liquidity is top blocker** — consider requiring liquidity OR structure break (not both) for v1 confluence, or widen sweep lookback in a future engine change.
4. **If using v2** — enable shadow mode: log v2 diagnostics while trading v1 until narrative completion rate is validated on live data.
5. **Verify closed-bar timing** — scanners on forming bars may miss sweeps that complete on bar close; confirm `MarketContextBuilder` uses closed bars only.