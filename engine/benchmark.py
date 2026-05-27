"""
Benchmark tracker — compares portfolio NAV against IWDA.L (or SPY).

On the first run we record the benchmark's starting price.
On each subsequent run we calculate the benchmark's total return since inception
and compare it to the portfolio's total return over the same period.
"""

import json
import logging
from pathlib import Path

from config.settings import BENCHMARK_TICKER, DATA_DIR
from engine.market_data import fetch_latest_price, fetch_prices

logger = logging.getLogger(__name__)

BENCHMARK_STATE_FILE = DATA_DIR / "benchmark_state.json"


def _load_state() -> dict:
    if BENCHMARK_STATE_FILE.exists():
        with open(BENCHMARK_STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state: dict) -> None:
    BENCHMARK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BENCHMARK_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def initialise_benchmark() -> float | None:
    """
    Record the benchmark's price at inception (call this once at portfolio start).
    Returns the starting price, or None on failure.
    """
    price = fetch_latest_price(BENCHMARK_TICKER)
    if price is None:
        logger.warning(f"Could not fetch starting price for benchmark {BENCHMARK_TICKER}")
        return None

    state = _load_state()
    if "starting_price" not in state:
        state["starting_price"] = price
        state["ticker"] = BENCHMARK_TICKER
        _save_state(state)
        logger.info(f"Benchmark {BENCHMARK_TICKER} initialised at {price:.4f}")

    return state["starting_price"]


def get_benchmark_return() -> dict:
    """
    Return benchmark performance since inception.

    Returns
    -------
    dict with keys: ticker, starting_price, current_price, return_pct, data_available
    """
    state = _load_state()
    if "starting_price" not in state:
        # Auto-initialise if not set up yet
        initialise_benchmark()
        state = _load_state()

    if "starting_price" not in state:
        return {"ticker": BENCHMARK_TICKER, "data_available": False}

    current_price = fetch_latest_price(BENCHMARK_TICKER)
    if current_price is None:
        return {"ticker": BENCHMARK_TICKER, "data_available": False}

    starting = state["starting_price"]
    return_pct = (current_price / starting - 1) * 100

    return {
        "ticker": BENCHMARK_TICKER,
        "starting_price": round(starting, 4),
        "current_price": round(current_price, 4),
        "return_pct": round(return_pct, 4),
        "data_available": True,
    }


def compare_to_benchmark(portfolio_return_pct: float) -> dict:
    """Return alpha (portfolio return minus benchmark return) in percentage points."""
    bm = get_benchmark_return()
    if not bm.get("data_available"):
        return {**bm, "portfolio_return_pct": portfolio_return_pct, "alpha_pp": None}

    alpha = portfolio_return_pct - bm["return_pct"]
    return {
        **bm,
        "portfolio_return_pct": round(portfolio_return_pct, 4),
        "alpha_pp": round(alpha, 4),
    }
