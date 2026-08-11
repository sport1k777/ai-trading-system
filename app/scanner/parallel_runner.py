"""Parallel symbol scanning with resource limits."""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

from app.config import SCANNER_CPU_LIMIT_PCT, SCANNER_MAX_WORKERS, SCANNER_RAM_LIMIT_MB

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _auto_worker_count(symbol_count: int) -> int:
    cpu = os.cpu_count() or 4
    cap = max(1, int(cpu * SCANNER_CPU_LIMIT_PCT / 100.0))
    if SCANNER_MAX_WORKERS > 0:
        cap = min(cap, SCANNER_MAX_WORKERS)
    return max(1, min(cap, symbol_count, 16))


def scan_symbols_parallel(
    symbols: list[str],
    worker_fn: Callable[[str], T],
    *,
    max_workers: int | None = None,
) -> tuple[list[T], int]:
    """Run *worker_fn* per symbol; isolate failures; return (results, failure_count)."""
    if not symbols:
        return [], 0

    workers = max_workers if max_workers is not None else _auto_worker_count(len(symbols))
    results: list[T] = []
    failures = 0
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scan") as pool:
        futures = {pool.submit(worker_fn, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                results.append(future.result())
            except Exception:
                failures += 1
                logger.exception("Parallel scan failed for %s", sym)

    elapsed = time.monotonic() - started
    logger.info(
        "Parallel scan | symbols=%d workers=%d failures=%d elapsed=%.2fs ram_limit_mb=%d",
        len(symbols),
        workers,
        failures,
        elapsed,
        SCANNER_RAM_LIMIT_MB,
    )
    return results, failures


def estimate_scan_duration(symbol_count: int, *, seconds_per_symbol: float = 0.35) -> float:
    """Rough cycle-time estimate given parallel workers."""
    workers = _auto_worker_count(symbol_count)
    return (symbol_count / workers) * seconds_per_symbol
