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
