from dotenv import load_dotenv
import os

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

TESTNET = os.getenv("TESTNET", "true").lower() in ("1", "true", "yes")

DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSDT")
DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "15")
DEFAULT_CANDLE_LIMIT = int(os.getenv("DEFAULT_CANDLE_LIMIT", "250"))
BACKTEST_CANDLE_LIMIT = int(os.getenv("BACKTEST_CANDLE_LIMIT", "1000"))

SCANNER_SYMBOLS = [
    s.strip()
    for s in os.getenv(
        "SCANNER_SYMBOLS",
        "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT",
    ).split(",")
    if s.strip()
]

# --- Strategy parameters (optimized for quality over quantity) ---
MIN_ADX = float(os.getenv("MIN_ADX", "24"))
MIN_CONFLUENCE = int(os.getenv("MIN_CONFLUENCE", "5"))
STOP_ATR_MULT = float(os.getenv("STOP_ATR_MULT", "0.85"))
TP_R_MULT = float(os.getenv("TP_R_MULT", "2.2"))
MAX_STOP_ATR_MULT = float(os.getenv("MAX_STOP_ATR_MULT", "1.5"))
MIN_BARS_BETWEEN_TRADES = int(os.getenv("MIN_BARS_BETWEEN_TRADES", "5"))

SIGNAL_BUY_THRESHOLD = int(os.getenv("SIGNAL_BUY_THRESHOLD", "55"))
SIGNAL_SELL_THRESHOLD = int(os.getenv("SIGNAL_SELL_THRESHOLD", "-55"))

BACKTEST_WARMUP_BARS = int(os.getenv("BACKTEST_WARMUP_BARS", "250"))
BACKTEST_MAX_HOLD_BARS = int(os.getenv("BACKTEST_MAX_HOLD_BARS", "30"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

BACKTEST_CACHE_PATH = os.getenv("BACKTEST_CACHE_PATH", ".cache/backtest_candles.csv")

# --- AI Signal Engine ---
AI_CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "90"))

AI_FEATURE_WEIGHTS = {
    "EMA": 1.5,
    "RSI": 1.2,
    "MACD": 1.3,
    "ADX": 1.0,
    "ATR": 0.8,
    "VWAP": 1.2,
    "Bollinger Bands": 1.4,
    "Volume": 1.0,
    "Volume Profile": 1.1,
    "Market Structure": 1.6,
    "Liquidity Sweeps": 1.5,
    "Order Blocks": 1.4,
    "Fair Value Gaps": 1.3,
    "Support/Resistance": 1.3,
    "Trend Strength": 1.5,
    "Multi-Timeframe": 1.8,
    "Volatility": 0.9,
    "Momentum": 1.2,
    "Session Strength": 0.7,
    "Candle Structure": 1.1,
    "BOS": 1.4,
    "CHOCH": 1.3,
}
