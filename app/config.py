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
TP_MIN_RR_TP1 = float(os.getenv("TP_MIN_RR_TP1", "1.5"))
TP_MIN_RR_TP2 = float(os.getenv("TP_MIN_RR_TP2", "2.5"))
TP_MIN_RR_TP3 = float(os.getenv("TP_MIN_RR_TP3", "3.5"))
MAX_STOP_ATR_MULT = float(os.getenv("MAX_STOP_ATR_MULT", "1.5"))
MIN_STOP_ATR_MULT = float(os.getenv("MIN_STOP_ATR_MULT", "0.25"))
MIN_BARS_BETWEEN_TRADES = int(os.getenv("MIN_BARS_BETWEEN_TRADES", "5"))

SIGNAL_BUY_THRESHOLD = int(os.getenv("SIGNAL_BUY_THRESHOLD", "55"))
SIGNAL_SELL_THRESHOLD = int(os.getenv("SIGNAL_SELL_THRESHOLD", "-55"))

BACKTEST_WARMUP_BARS = int(os.getenv("BACKTEST_WARMUP_BARS", "250"))
BACKTEST_MAX_HOLD_BARS = int(os.getenv("BACKTEST_MAX_HOLD_BARS", "30"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

BACKTEST_CACHE_PATH = os.getenv("BACKTEST_CACHE_PATH", ".cache/backtest_candles.csv")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("1", "true", "yes")
# Telegram notification gate only — does not affect engine entry/scoring thresholds.
TELEGRAM_NOTIFY_MIN_CONFIDENCE = float(os.getenv("TELEGRAM_NOTIFY_MIN_CONFIDENCE", "70"))

# --- Signal Engine selection ---
SIGNAL_ENGINE_VERSION = os.getenv("SIGNAL_ENGINE_VERSION", "v1").lower()

# --- Signal Engine PRO ---
PRO_MIN_CONDITIONS = int(os.getenv("PRO_MIN_CONDITIONS", "5"))
PRO_MIN_CONFIDENCE = float(os.getenv("PRO_MIN_CONFIDENCE", "65"))
PRO_MIN_DIRECTION_GAP = float(os.getenv("PRO_MIN_DIRECTION_GAP", "10"))
PRO_CONDITION_WEIGHTS = {
    "structure": float(os.getenv("PRO_WEIGHT_STRUCTURE", "15")),
    "fvg": float(os.getenv("PRO_WEIGHT_FVG", "12")),
    "order_block": float(os.getenv("PRO_WEIGHT_ORDER_BLOCK", "12")),
    "liquidity": float(os.getenv("PRO_WEIGHT_LIQUIDITY", "15")),
    "ema_trend": float(os.getenv("PRO_WEIGHT_EMA_TREND", "12")),
    "rsi": float(os.getenv("PRO_WEIGHT_RSI", "10")),
    "volume": float(os.getenv("PRO_WEIGHT_VOLUME", "12")),
    "atr": float(os.getenv("PRO_WEIGHT_ATR", "12")),
    "adx": float(os.getenv("PRO_WEIGHT_ADX", "10")),
    "htf": float(os.getenv("PRO_WEIGHT_HTF", "12")),
}

# --- Signal Engine PRO V2 ---
PRO_V2_HTF_INTERVAL = os.getenv("PRO_V2_HTF_INTERVAL", "60")
PRO_V2_MIN_ADX = float(os.getenv("PRO_V2_MIN_ADX", "22"))
PRO_V2_MIN_RR = float(os.getenv("PRO_V2_MIN_RR", "1.5"))
PRO_V2_MIN_GRADE = os.getenv("PRO_V2_MIN_GRADE", "A")
PRO_V2_SESSION_FILTER = os.getenv("PRO_V2_SESSION_FILTER", "false").lower() in ("1", "true", "yes")
PRO_V2_BARS_PER_HTF = int(os.getenv("PRO_V2_BARS_PER_HTF", "4"))

# --- Structure persistence (closed-bar, no look-ahead) ---
STRUCTURE_BOS_LOOKBACK = int(os.getenv("STRUCTURE_BOS_LOOKBACK", "12"))
STRUCTURE_CHOCH_LOOKBACK = int(os.getenv("STRUCTURE_CHOCH_LOOKBACK", "12"))
STRUCTURE_HTF_LOOKBACK = int(os.getenv("STRUCTURE_HTF_LOOKBACK", "8"))

# --- Adaptive market regime ---
REGIME_STRONG_ADX = float(os.getenv("REGIME_STRONG_ADX", "28"))
REGIME_WEAK_ADX = float(os.getenv("REGIME_WEAK_ADX", "18"))
REGIME_HIGH_VOL_ATR_PCT = float(os.getenv("REGIME_HIGH_VOL_ATR_PCT", "3.5"))
REGIME_LOW_VOL_ATR_PCT = float(os.getenv("REGIME_LOW_VOL_ATR_PCT", "0.35"))
REGIME_POI_TOLERANCE_HIGH = float(os.getenv("REGIME_POI_TOLERANCE_HIGH", "0.005"))
REGIME_POI_TOLERANCE_LOW = float(os.getenv("REGIME_POI_TOLERANCE_LOW", "0.002"))
REGIME_LOW_VOL_TP_R_MULT = float(os.getenv("REGIME_LOW_VOL_TP_R_MULT", "0.85"))

# --- Signal validation (pre-Telegram) ---
VALIDATION_MIN_RISK_PCT = float(os.getenv("VALIDATION_MIN_RISK_PCT", "0.3"))
VALIDATION_MAX_RISK_PCT = float(os.getenv("VALIDATION_MAX_RISK_PCT", "3.0"))
VALIDATION_ENTRY_MAX_DISTANCE_PCT = float(os.getenv("VALIDATION_ENTRY_MAX_DISTANCE_PCT", "1.0"))
VALIDATION_RR_TOLERANCE_PCT = float(os.getenv("VALIDATION_RR_TOLERANCE_PCT", "0.05"))
VALIDATION_PRICE_DRIFT_MAX_PCT = float(os.getenv("VALIDATION_PRICE_DRIFT_MAX_PCT", "0.25"))
SIGNAL_DUPLICATE_WINDOW_MINUTES = int(os.getenv("SIGNAL_DUPLICATE_WINDOW_MINUTES", "30"))

# --- Expanded scanner universe ---
SCANNER_SYMBOL_TARGET = int(os.getenv("SCANNER_SYMBOL_TARGET", "150"))
SCANNER_MIN_TURNOVER_24H = float(os.getenv("SCANNER_MIN_TURNOVER_24H", "500000"))
SCANNER_MAX_SPREAD_PCT = float(os.getenv("SCANNER_MAX_SPREAD_PCT", "0.5"))
SCANNER_MAX_WORKERS = int(os.getenv("SCANNER_MAX_WORKERS", "0"))  # 0 = auto from CPU
SCANNER_UNIVERSE_CACHE_SECONDS = int(os.getenv("SCANNER_UNIVERSE_CACHE_SECONDS", "3600"))
SCANNER_CPU_LIMIT_PCT = float(os.getenv("SCANNER_CPU_LIMIT_PCT", "80"))
SCANNER_RAM_LIMIT_MB = int(os.getenv("SCANNER_RAM_LIMIT_MB", "2048"))

# --- Two-stage scanner ---
FAST_SCAN_ENABLED = os.getenv("FAST_SCAN_ENABLED", "true").lower() in ("1", "true", "yes")
FAST_SCAN_CANDIDATE_COUNT = int(os.getenv("FAST_SCAN_CANDIDATE_COUNT", "25"))
FAST_SCAN_MIN_UNIVERSE = int(os.getenv("FAST_SCAN_MIN_UNIVERSE", "30"))

# --- 24/7 Signal Service ---
SIGNAL_SERVICE_SCAN_INTERVAL_SECONDS = int(
    os.getenv("SIGNAL_SERVICE_SCAN_INTERVAL_SECONDS", "60")
)
SIGNAL_SERVICE_SENT_STORE_PATH = os.getenv(
    "SIGNAL_SERVICE_SENT_STORE_PATH",
    ".cache/telegram_sent_signals.json",
)
SIGNAL_SERVICE_ERROR_BACKOFF_SECONDS = int(
    os.getenv("SIGNAL_SERVICE_ERROR_BACKOFF_SECONDS", "10")
)
SIGNAL_SERVICE_RECONNECT_AFTER_ERRORS = int(
    os.getenv("SIGNAL_SERVICE_RECONNECT_AFTER_ERRORS", "3")
)

# --- Multi-source intelligence (signal research only — read-only providers) ---
INTELLIGENCE_ENABLED = os.getenv("INTELLIGENCE_ENABLED", "true").lower() in ("1", "true", "yes")
INTELLIGENCE_CACHE_SECONDS = int(os.getenv("INTELLIGENCE_CACHE_SECONDS", "300"))
INTELLIGENCE_BYBIT_MARKET_ENABLED = os.getenv(
    "INTELLIGENCE_BYBIT_MARKET_ENABLED", "true"
).lower() in ("1", "true", "yes")
INTELLIGENCE_NEWS_ENABLED = os.getenv("INTELLIGENCE_NEWS_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
INTELLIGENCE_NEWS_RSS_URLS = [
    u.strip()
    for u in os.getenv(
        "INTELLIGENCE_NEWS_RSS_URLS",
        "https://www.coindesk.com/arc/outboundfeeds/rss/,"
        "https://cointelegraph.com/rss",
    ).split(",")
    if u.strip()
]
INTELLIGENCE_SOCIAL_ENABLED = os.getenv("INTELLIGENCE_SOCIAL_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
INTELLIGENCE_ONCHAIN_ENABLED = os.getenv("INTELLIGENCE_ONCHAIN_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
ONCHAIN_API_KEY = os.getenv("ONCHAIN_API_KEY", "")
INTELLIGENCE_FUNDAMENTAL_ENABLED = os.getenv(
    "INTELLIGENCE_FUNDAMENTAL_ENABLED", "true"
).lower() in ("1", "true", "yes")
INTELLIGENCE_FRESHNESS_HALF_LIFE_MINUTES = float(
    os.getenv("INTELLIGENCE_FRESHNESS_HALF_LIFE_MINUTES", "120")
)
INTELLIGENCE_MAX_NEWS_AGE_HOURS = float(os.getenv("INTELLIGENCE_MAX_NEWS_AGE_HOURS", "48"))
INTELLIGENCE_BLOCK_NEGATIVE_NEWS = os.getenv(
    "INTELLIGENCE_BLOCK_NEGATIVE_NEWS", "true"
).lower() in ("1", "true", "yes")
INTELLIGENCE_MIN_COMPOSITE_SCORE = float(os.getenv("INTELLIGENCE_MIN_COMPOSITE_SCORE", "55"))
INTELLIGENCE_WEIGHT_TECHNICAL = float(os.getenv("INTELLIGENCE_WEIGHT_TECHNICAL", "0.30"))
INTELLIGENCE_WEIGHT_REGIME = float(os.getenv("INTELLIGENCE_WEIGHT_REGIME", "0.15"))
INTELLIGENCE_WEIGHT_LIQUIDITY = float(os.getenv("INTELLIGENCE_WEIGHT_LIQUIDITY", "0.10"))
INTELLIGENCE_WEIGHT_MOMENTUM = float(os.getenv("INTELLIGENCE_WEIGHT_MOMENTUM", "0.10"))
INTELLIGENCE_WEIGHT_NEWS = float(os.getenv("INTELLIGENCE_WEIGHT_NEWS", "0.10"))
INTELLIGENCE_WEIGHT_SOCIAL = float(os.getenv("INTELLIGENCE_WEIGHT_SOCIAL", "0.05"))
INTELLIGENCE_WEIGHT_FUNDAMENTAL = float(os.getenv("INTELLIGENCE_WEIGHT_FUNDAMENTAL", "0.08"))
INTELLIGENCE_WEIGHT_ONCHAIN = float(os.getenv("INTELLIGENCE_WEIGHT_ONCHAIN", "0.07"))
CANDIDATE_DIAGNOSTICS_PATH = os.getenv(
    "CANDIDATE_DIAGNOSTICS_PATH", ".cache/candidate_diagnostics.jsonl"
)
MIN_REWARD_ATR_MULT = float(os.getenv("MIN_REWARD_ATR_MULT", "0.35"))
ESTIMATED_FEE_PCT = float(os.getenv("ESTIMATED_FEE_PCT", "0.06"))
ESTIMATED_SLIPPAGE_PCT = float(os.getenv("ESTIMATED_SLIPPAGE_PCT", "0.05"))

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
