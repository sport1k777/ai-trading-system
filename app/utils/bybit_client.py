"""Read-only Bybit market data client.

SIGNAL-ONLY SYSTEM: this module must never place, amend, or cancel orders,
open/close positions, or call any Bybit trading or account-mutation endpoints.
Allowed operations: public market data (klines, tickers, server time) only.
"""

from __future__ import annotations

import logging

import pandas as pd
from pybit.unified_trading import HTTP

from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, TESTNET
from app.utils.ssl_ca import ensure_ca_bundle

logger = logging.getLogger(__name__)

# Explicit allow-list — no trading / account mutation methods.
_ALLOWED_SESSION_METHODS = frozenset({
    "get_server_time",
    "get_tickers",
    "get_kline",
    "get_instruments_info",
})


class _ReadOnlySession:
    """Proxy that blocks any Bybit session call outside the market-data allow-list."""

    __slots__ = ("_session",)

    def __init__(self, session: HTTP) -> None:
        self._session = session

    def __getattr__(self, name: str):
        if name not in _ALLOWED_SESSION_METHODS:
            raise RuntimeError(
                f"SIGNAL-ONLY: Bybit trading endpoint blocked ({name!r}). "
                "This system must not place or manage orders."
            )
        return getattr(self._session, name)


class BybitClient:
    """Single shared Bybit HTTP session for read-only market data."""

    def __init__(self):
        ensure_ca_bundle()
        self.session = HTTP(
            testnet=TESTNET,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
        )

    def __getattribute__(self, name: str):
        attr = object.__getattribute__(self, name)
        if name == "session":
            return _ReadOnlySession(attr)
        return attr

    def get_server_time(self):
        return self.session.get_server_time()

    def get_tickers(self, category: str = "linear", symbol: str | None = None):
        params: dict = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return self.session.get_tickers(**params)

    def get_instruments_info(
        self,
        category: str = "linear",
        *,
        symbol: str | None = None,
        limit: int = 1000,
    ) -> dict:
        params: dict = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        return self.session.get_instruments_info(**params)

    def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15",
        limit: int = 250,
    ) -> pd.DataFrame:
        response = self.session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit,
        )

        if response.get("retCode", 0) != 0:
            msg = response.get("retMsg", "Unknown Bybit API error")
            raise RuntimeError(f"Bybit kline request failed: {msg}")

        data = response["result"]["list"]
        if not data:
            raise ValueError(f"No candle data returned for {symbol}")

        df = pd.DataFrame(
            data,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ],
        )

        df = df.astype(
            {
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": float,
                "turnover": float,
            }
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"].astype("int64"),
            unit="ms",
        )

        df = df.sort_values("timestamp").reset_index(drop=True)
        logger.info(
            "Bybit kline OK | GET /v5/market/kline | symbol=%s interval=%s rows=%d",
            symbol,
            interval,
            len(df),
        )
        return df

    def reconnect(self) -> None:
        """Create a fresh HTTP session after connectivity failures."""
        logger.warning("Resetting Bybit HTTP session")
        ensure_ca_bundle()
        self.session = HTTP(
            testnet=TESTNET,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
        )


if __name__ == "__main__":
    from app.utils.logging_config import setup_logging

    setup_logging(__name__)
    client = BybitClient()

    print("Server Time:")
    print(client.get_server_time())

    print("\nBTC Ticker:")
    tickers = client.get_tickers()
    for coin in tickers["result"]["list"]:
        if coin["symbol"] == "BTCUSDT":
            print(coin)
            break
