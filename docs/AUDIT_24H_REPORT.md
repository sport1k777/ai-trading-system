# 24-Hour Gate Audit Report

- Engine: **v1**
- Window: **96** closed 15m bars per symbol (~24h)
- Symbols: **BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT**
- Total scans: **480**

## Engine outcomes

- BUY: **7**
- SELL: **4**
- WAIT: **469**
- Telegram-eligible (current): **11**

## Gate failure rates

| Gate | PASS | FAIL | FAIL % |
|------|------|------|--------|
| ADX | 262 | 218 | 45% |
| ATR | 480 | 0 | 0% |
| BOS | 237 | 243 | 51% |
| CHOCH | 200 | 280 | 58% |
| EMA | 199 | 281 | 59% |
| FVG | 153 | 327 | 68% |
| HTF | 282 | 198 | 41% |
| Liquidity | 450 | 30 | 6% |
| Order Block | 454 | 26 | 5% |
| RSI | 423 | 57 | 12% |
| Regime | 238 | 242 | 50% |
| Trend | 264 | 216 | 45% |
| Volume | 59 | 421 | 88% |

## Regime blocks after confluence pick

- **Strong Trend requires BOS**: 12
- Confluence pick passed: **23** scans

## Near-miss analysis

- **confidence_shortfall_60_64**: 32
- **four_plus_hits_high_score**: 12
- **confluence_pass_regime_block**: 12

## Confidence distribution (best side)

- **60-64**: 32
- **65-69**: 12
- **70+**: 11
- **<60**: 425

## Counterfactual threshold grid (Telegram gate fixed)

| conditions | confidence | gap | alerts/24h |
|------------|------------|-----|------------|
| 4 | 60 | 6 | 11 |
| 4 | 60 | 8 | 11 |
| 4 | 60 | 10 | 11 |
| 4 | 62 | 6 | 11 |
| 4 | 62 | 8 | 11 |
| 4 | 62 | 10 | 11 |
| 4 | 65 | 6 | 11 |
| 4 | 65 | 8 | 11 |
| 4 | 65 | 10 | 11 |
| 5 | 60 | 6 | 11 |
| 5 | 60 | 8 | 11 |
| 5 | 60 | 10 | 11 |
| 5 | 62 | 6 | 11 |
| 5 | 62 | 8 | 11 |
| 5 | 62 | 10 | 11 |
| 5 | 65 | 6 | 11 |
| 5 | 65 | 8 | 11 |
| 5 | 65 | 10 | 11 |

## Recommendations (data-driven)

Current 24h bar-close replay: **480** scans, engine BUY/SELL **11**, Telegram alerts **11** (threshold 70%).
The engine already emits more than the 2–5/day target on closed-bar replay; prefer **tightening delivery filters** (Telegram gate, per-symbol cooldown) rather than lowering PRO confluence thresholds.
Near-miss breakdown (engine WAIT but close to thresholds):
- **confidence_shortfall_60_64**: 32 (6.7% of scans)
- **four_plus_hits_high_score**: 12 (2.5% of scans)
- **confluence_pass_regime_block**: 12 (2.5% of scans)
Regime blocks after confluence pick (current thresholds):
- **Strong Trend requires BOS**: 12
Counterfactual grid did not reduce below current alert count because all 11 alerts already meet the strictest grid point; use Telegram/cooldown tuning.
Top setup-filter failure rates (diagnostic checklist, candidate direction):
- **Volume**: FAIL 421/480 (88%)
- **FVG**: FAIL 327/480 (68%)
- **EMA**: FAIL 281/480 (59%)
- **CHOCH**: FAIL 280/480 (58%)
- **BOS**: FAIL 243/480 (51%)