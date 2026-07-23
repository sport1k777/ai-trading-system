# AI Trading System

Bybit linear futures analysis toolkit combining ICT-style market structure
(BOS, CHOCH, liquidity sweeps, order blocks, FVG) with EMA/RSI/MACD indicators.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Add your Bybit API credentials to .env
```

## Usage

```bash
# Single-symbol analysis
python -m app.engine
# or after install:
trading-engine

# Multi-symbol scanner
python -m app.scanner
trading-scanner

# 24/7 Telegram signal service
python -m app.services.signal_service
python scripts/run_signal_service.py
trading-signals

# Signal Engine PRO V2 evaluation
PYTHONPATH=. python scripts/pro_v2_eval.py

# Walk-forward backtest with stop-loss / take-profit simulation
python -m app.backtester
trading-backtest
```

## Configuration

All settings live in `.env` (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `TESTNET` | `true` | Use Bybit testnet |
| `DEFAULT_SYMBOL` | `BTCUSDT` | Default trading pair |
| `DEFAULT_INTERVAL` | `15` | Candle interval (minutes) |
| `DEFAULT_CANDLE_LIMIT` | `250` | Candles fetched per request |
| `SIGNAL_BUY_THRESHOLD` | `55` | Minimum score for BUY |
| `SIGNAL_SELL_THRESHOLD` | `-55` | Maximum score for SELL |
| `SCANNER_SYMBOLS` | BTC,ETH,SOL,XRP,DOGE | Comma-separated symbols |
| `SIGNAL_ENGINE_VERSION` | `v1` | `v1` (checklist PRO) or `v2` (sequential SMC) |
| `PRO_V2_MIN_GRADE` | `A` | Minimum grade to emit signals in v2 |
| `PRO_V2_MIN_RR` | `2.0` | Minimum risk/reward for v2 |

## Strategy

Regime-adaptive system with three setup types:

| Regime | ADX | Setup | Logic |
|---|---|---|---|
| Range | ≤ 26 | Mean reversion | Fade BB extremes, target BB mid |
| Transition | 26–38 | Pullback | Enter EMA20 pullbacks with the trend |
| Strong trend | ≥ 38 | Momentum | Continue trend (avoid exhausted RSI) |

Each setup uses tailored stop/TP via `RiskManager` (0.75–1.2 ATR stops, 2–2.5R targets).

## Tests

```bash
pytest
```

## Architecture

```
Bybit API → CandleCollector → SignalIndicators → Analyzers → SignalGenerator → RiskManager
```

All orchestration goes through `app.pipeline.TradingPipeline` to avoid duplicate work.

## VPS deployment (Git)

Production deploys use Git on the VPS — see **[docs/GIT_DEPLOYMENT.md](docs/GIT_DEPLOYMENT.md)**.

```bash
# Inspect state (none / manual / git)
ssh root@YOUR_VPS 'bash -s' < scripts/deploy/inspect.sh

# One-time migration from manual/rsync install (preserves .env, venv, systemd)
ssh root@YOUR_VPS 'sudo bash /opt/ai-trading-system/scripts/deploy/deploy.sh'

# Routine updates after migration
ssh root@YOUR_VPS 'sudo bash /opt/ai-trading-system/scripts/deploy/update.sh'
```

Legacy laptop rsync deploy: `scripts/deploy/contabo_deploy.sh`

Pre-deploy check: `python scripts/validate_production.py`  
Full audit: **[docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)**

## Disclaimer

This is a signal analysis and backtesting tool. It does **not** place live orders.
Use at your own risk.
