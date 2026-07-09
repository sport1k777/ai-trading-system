# Signal Engine PRO V2

## Architecture

```
CandleCollector → MarketContextBuilder → SignalEngineProV2
                      ↓
              Regime Gates (ATR, ADX, Session, Structure)
                      ↓
              Setup Sequence (Sweep → Displacement → POI → Confirm)
                      ↓
              Confirmations (EMA, RSI, VWAP, Volume Profile)
                      ↓
              RiskManagerV2 + Grader (A+/A/B/C)
```

## Modules

| Path | Purpose |
|---|---|
| `app/analysis/market_context.py` | Single-pass analyzer execution |
| `app/analysis/pro_v2/engine.py` | Main orchestrator |
| `app/analysis/pro_v2/htf_bias.py` | HTF trend/structure bias |
| `app/analysis/pro_v2/regime_gate.py` | ATR, ADX, session gates |
| `app/analysis/pro_v2/dealing_range.py` | Premium/discount zones |
| `app/analysis/pro_v2/setup_sequence.py` | Sequential narrative |
| `app/analysis/pro_v2/confirmations.py` | EMA, RSI, VWAP, POC |
| `app/analysis/pro_v2/grader.py` | A+/A/B/C grading |
| `app/risk/risk_manager_v2.py` | Risk + liquidity TPs |
| `app/backtest/pro_backtester.py` | Walk-forward backtest |

## Configuration

See `.env.example` for all `PRO_V2_*` and `SIGNAL_ENGINE_VERSION` settings.

## Testing

```bash
PYTHONPATH=. pytest tests/test_pro_v2.py -v
python scripts/pro_v2_eval.py
```

## Production readiness

- Feature flag for safe rollback
- Closed-bar analysis reduces repaint
- HTF uses fetched 1h candles or resampled LTF
- Telegram formatter shows grade
- systemd service compatible without changes
