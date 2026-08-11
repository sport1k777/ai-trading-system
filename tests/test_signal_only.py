"""Verify the repository remains a signal-only system (no trade execution)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.utils.bybit_client import BybitClient, _ReadOnlySession

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories that may reference simulated/backtest trade logic only.
_SCAN_SKIP_DIRS = {
    ".git",
    ".cache",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}

# Forbidden trading API / execution patterns in application code.
_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("place_order", re.compile(r"\bplace_order\b")),
    ("create_order", re.compile(r"\bcreate_order\b")),
    ("submit_order", re.compile(r"\bsubmit_order\b")),
    ("cancel_order", re.compile(r"\bcancel_order\b")),
    ("amend_order", re.compile(r"\bamend_order\b")),
    ("set_leverage", re.compile(r"\bset_leverage\b")),
    ("set_trading_stop", re.compile(r"\bset_trading_stop\b")),
    ("close_position", re.compile(r"\bclose_position\b")),
    ("open_position", re.compile(r"\bopen_position\b")),
    ("execute_trade", re.compile(r"\bexecute_trade\b")),
    ("/v5/order", re.compile(r"/v5/order")),
    ("/v5/position", re.compile(r"/v5/position")),
    ("get_open_orders", re.compile(r"\bget_open_orders\b")),
    ("wallet_balance", re.compile(r"\bwallet_balance\b")),
)

# Files allowed to mention simulate_trade (backtest / research only).
_SIMULATE_TRADE_ALLOWED = {
    "app/risk/risk_manager.py",
    "app/backtester.py",
    "app/backtest/pro_backtester.py",
    "app/analysis/filter_calibrator.py",
    "app/analysis/production_optimizer.py",
    "app/analysis/self_learning_engine.py",
    "scripts/long_term_eval.py",
    "scripts/ai_tune_and_eval.py",
}


def _iter_repo_files() -> list[Path]:
    scan_roots = ("app", "scripts", "deploy")
    files: list[Path] = []
    for root_name in scan_roots:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _SCAN_SKIP_DIRS for part in path.parts):
                continue
            if path.suffix not in {".py", ".sh", ".service"}:
                continue
            files.append(path)
    return files


def test_repo_has_no_order_execution_calls():
    """Full-repo scan: no live trading endpoint or order placement calls."""
    violations: list[str] = []

    for path in _iter_repo_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")

        for label, pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel}: matched forbidden pattern {label!r}")

        if "simulate_trade" in text and rel not in _SIMULATE_TRADE_ALLOWED:
            if rel.startswith("tests/"):
                continue
            violations.append(
                f"{rel}: simulate_trade outside approved backtest/research modules"
            )

    assert not violations, "Signal-only violations found:\n" + "\n".join(violations)


def test_bybit_client_blocks_trading_session_methods():
    """Bybit session proxy must reject any method outside the market-data allow-list."""

    class FakeSession:
        def get_kline(self, **kwargs):
            return {"retCode": 0, "result": {"list": []}}

        def place_order(self, **kwargs):
            return {"retCode": 0}

    proxy = _ReadOnlySession(FakeSession())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="SIGNAL-ONLY"):
        proxy.place_order(symbol="BTCUSDT", side="Buy", qty="1")

    with pytest.raises(RuntimeError, match="SIGNAL-ONLY"):
        proxy.get_wallet_balance(coin="USDT")


def test_bybit_client_allows_market_data_methods():
    class FakeSession:
        def get_server_time(self):
            return {"retCode": 0, "result": {"timeSecond": "1"}}

    proxy = _ReadOnlySession(FakeSession())  # type: ignore[arg-type]
    assert proxy.get_server_time()["retCode"] == 0


def test_bybit_client_wraps_session_on_access():
    client = BybitClient.__new__(BybitClient)
    object.__setattr__(client, "session", object())
    wrapped = client.__getattribute__("session")
    assert isinstance(wrapped, _ReadOnlySession)
