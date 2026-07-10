# Adaptive Market Regime Detection

The PRO signal engine classifies each scan into a **trend regime** and **volatility regime**, then adapts confirmation logic without lowering confidence thresholds.

## Regime taxonomy

| Trend | Volatility overlay |
|-------|-------------------|
| Strong Trend | High / Low Volatility |
| Weak Trend | High / Low Volatility |
| Range | High / Low Volatility |

Detection uses ADX, ATR%, LTF trend/structure, and HTF trend (`app/analysis/market_regime.py`).

## Adaptive rules

### Strong Trend
- Requires: BOS, HTF alignment, EMA, ADX
- Boosts structure and EMA confluence weights

### Weak Trend
- Requires: BOS **or** CHOCH, HTF alignment
- ADX weighted moderately (not a hard gate)

### Range
- Prioritizes liquidity sweeps and CHOCH
- Reduces BOS weight; ADX optional when volatility is low

### High Volatility
- ATR gate widened to 8%
- OB/FVG proximity tolerance 0.5%

### Low Volatility
- Tighter stops (`stop_mult_factor=0.85`)
- Lower TP R-multiple (`tp_r_mult=0.85`)
- OB/FVG proximity tolerance 0.2%

## Configuration

```env
REGIME_STRONG_ADX=28
REGIME_WEAK_ADX=18
REGIME_HIGH_VOL_ATR_PCT=3.5
REGIME_LOW_VOL_ATR_PCT=0.35
REGIME_POI_TOLERANCE_HIGH=0.005
REGIME_POI_TOLERANCE_LOW=0.002
REGIME_LOW_VOL_TP_R_MULT=0.85
```

Confidence gates are **unchanged**: `PRO_MIN_CONFIDENCE=65`, `TELEGRAM_NOTIFY_MIN_CONFIDENCE=90`.

## Diagnostics

Per-scan logs include `Market regime:` and `Regime gate:` checks.

Aggregate report (24h replay at 60s cycles ≈ 1440 scans/symbol):

```bash
python scripts/regime_diagnostic_report.py 288
```

Output: `docs/REGIME_DIAGNOSTIC_REPORT.md`
