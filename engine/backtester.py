"""
Backtester — replays the last N years of price data through the agent system.

Rather than calling Claude on every historical day (expensive and slow),
the backtester runs a simplified rule-based replay by default, with an option
to run the full Claude-powered agents on a sampled set of dates (e.g. weekly).

Usage
-----
    from engine.backtester import run_backtest
    results = run_backtest(years=2, sample_interval_days=7)
"""

import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta

import pandas as pd

from config.settings import STARTING_CAPITAL_GBP, BENCHMARK_TICKER, BACKTEST_YEARS
from engine.market_data import fetch_prices, fetch_all_holdings

logger = logging.getLogger(__name__)


def run_backtest(
    years: int = BACKTEST_YEARS,
    initial_allocations: dict[str, float] | None = None,
) -> dict:
    """
    Simple buy-and-hold backtest: start with equal-weight across all tracked
    tickers, hold for *years*, compare to benchmark.

    Parameters
    ----------
    years               : how many years of history to replay
    initial_allocations : optional dict of {ticker: weight} where weights sum to 1.
                          Defaults to equal-weight across all holdings.

    Returns
    -------
    dict with keys: start_date, end_date, portfolio_return_pct,
                    benchmark_return_pct, alpha_pp, nav_series (list of dicts),
                    position_returns (dict of {ticker: return_pct})
    """
    logger.info(f"Starting {years}-year buy-and-hold backtest")

    all_data = fetch_all_holdings()
    if not all_data:
        return {"error": "No price data available for backtest"}

    # Align all series to a common date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=years * 365)

    # Build a closing-price matrix
    closes: dict[str, pd.Series] = {}
    for ticker, df in all_data.items():
        if "Close" in df.columns:
            s = df["Close"].dropna()
            s = s[s.index.date >= start_date]
            if not s.empty:
                closes[ticker] = s

    if not closes:
        return {"error": "Insufficient historical data for the requested period"}

    # Determine tickers to include (exclude benchmark from portfolio)
    portfolio_tickers = [t for t in closes if t != BENCHMARK_TICKER]

    # Build allocations
    if initial_allocations is None:
        n = len(portfolio_tickers)
        initial_allocations = {t: 1.0 / n for t in portfolio_tickers}

    # Simulate: buy on first available date, sell on last
    position_returns: dict[str, float] = {}
    portfolio_total_return = 0.0

    for ticker, weight in initial_allocations.items():
        if ticker not in closes:
            logger.warning(f"No data for {ticker} in backtest period — skipping")
            continue
        series = closes[ticker]
        start_price = float(series.iloc[0])
        end_price = float(series.iloc[-1])
        ret = (end_price / start_price - 1) * 100
        position_returns[ticker] = round(ret, 2)
        portfolio_total_return += weight * ret

    # Benchmark return
    bm_return = None
    if BENCHMARK_TICKER in closes:
        bm = closes[BENCHMARK_TICKER]
        bm_return = round((float(bm.iloc[-1]) / float(bm.iloc[0]) - 1) * 100, 2)

    alpha = round(portfolio_total_return - bm_return, 2) if bm_return is not None else None

    # Build a simple NAV time series using portfolio-weighted daily returns
    nav_series = _build_nav_series(closes, initial_allocations, portfolio_tickers)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "portfolio_return_pct": round(portfolio_total_return, 2),
        "benchmark_return_pct": bm_return,
        "alpha_pp": alpha,
        "position_returns": position_returns,
        "nav_series": nav_series,
    }


def _build_nav_series(
    closes: dict[str, pd.Series],
    allocations: dict[str, float],
    portfolio_tickers: list[str],
) -> list[dict]:
    """Build a daily NAV series for the backtested portfolio."""
    # Create a combined DataFrame with common dates
    frames = {t: closes[t] for t in portfolio_tickers if t in closes}
    if not frames:
        return []

    df = pd.DataFrame(frames)
    df = df.dropna(how="all")

    # Forward-fill missing prices (e.g. ASX closed on US trading days)
    df = df.ffill()

    # Normalise each column to start at 1
    start_prices = df.iloc[0]
    normalised = df / start_prices

    # Weighted portfolio value
    weights = pd.Series({t: allocations.get(t, 0.0) for t in df.columns})
    portfolio_index = (normalised * weights).sum(axis=1)

    nav_gbp_series = portfolio_index * STARTING_CAPITAL_GBP

    result = []
    for date, nav in nav_gbp_series.items():
        result.append({
            "date": str(date.date()) if hasattr(date, "date") else str(date),
            "nav_gbp": round(float(nav), 2),
        })
    return result
