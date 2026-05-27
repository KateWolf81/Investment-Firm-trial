"""
Market data layer — thin wrapper around yfinance.

Fetches OHLCV price data for all tickers in holdings.json and caches results
as CSV files under data/historical/ so we don't hammer the yfinance API on
every run.  All price data is returned as pandas DataFrames.

FX rates (AUD/GBP, USD/GBP) are fetched via yfinance currency pairs so the
simulation engine can convert non-GBP positions to GBP for NAV calculations.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from config.settings import HISTORICAL_DIR, BASE_DIR

logger = logging.getLogger(__name__)

# yfinance symbols for FX rates (price of 1 foreign unit in GBP)
FX_PAIRS = {
    "AUD": "AUDGBP=X",
    "USD": "USDGBP=X",
    "EUR": "EURGBP=X",
}


def _cache_path(ticker: str) -> Path:
    """Return the CSV cache file path for a given ticker."""
    safe = ticker.replace("/", "_").replace("=", "_")
    return HISTORICAL_DIR / f"{safe}.csv"


def fetch_prices(
    ticker: str,
    period_years: int = 2,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Return a DataFrame of daily OHLCV data for *ticker*.

    Uses a local CSV cache.  The cache is considered stale if the most recent
    row is more than 1 calendar day old (so a morning run re-fetches yesterday's
    close automatically).

    Parameters
    ----------
    ticker        : yfinance ticker symbol, e.g. "PYC.AX" or "OKLO"
    period_years  : how many years of history to fetch on a cache miss
    force_refresh : ignore the cache and always hit yfinance

    Returns
    -------
    DataFrame with columns [Open, High, Low, Close, Volume, Adj Close]
    indexed by date (timezone-naive).  Returns an empty DataFrame on failure.
    """
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(ticker)

    if not force_refresh and cache.exists():
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        if not df.empty:
            most_recent = df.index.max()
            # Cache is fresh enough if it contains data from yesterday or today
            cutoff = pd.Timestamp(datetime.now().date() - timedelta(days=1))
            if most_recent >= cutoff:
                logger.debug(f"Cache hit for {ticker}")
                return df

    logger.info(f"Fetching {period_years}y of data for {ticker} from yfinance")
    try:
        raw = yf.download(
            ticker,
            period=f"{period_years}y",
            auto_adjust=True,
            progress=False,
        )
        if raw.empty:
            logger.warning(f"yfinance returned no data for {ticker}")
            return pd.DataFrame()

        # yfinance sometimes returns MultiIndex columns — flatten them
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        raw.index = pd.to_datetime(raw.index).tz_localize(None)
        raw.to_csv(cache)
        return raw
    except Exception as exc:
        logger.error(f"Failed to fetch {ticker}: {exc}")
        return pd.DataFrame()


def fetch_latest_price(ticker: str) -> float | None:
    """
    Return the most recent closing price for *ticker*, or None on failure.
    Tries the cache first, falls back to a yfinance spot quote.
    """
    df = fetch_prices(ticker)
    if not df.empty and "Close" in df.columns:
        return float(df["Close"].iloc[-1])

    # Cache miss / stale — try a quick spot download
    try:
        spot = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
        if not spot.empty:
            if isinstance(spot.columns, pd.MultiIndex):
                spot.columns = spot.columns.get_level_values(0)
            return float(spot["Close"].iloc[-1])
    except Exception as exc:
        logger.error(f"Spot price fetch failed for {ticker}: {exc}")
    return None


def fetch_fx_rates() -> dict[str, float]:
    """
    Return a dict of {currency_code: rate_in_gbp}, e.g. {"USD": 0.79, "AUD": 0.51}.
    Falls back to hardcoded approximate rates if yfinance is unavailable.
    """
    rates: dict[str, float] = {}
    fallbacks = {"USD": 0.79, "AUD": 0.51, "EUR": 0.86}

    for currency, pair in FX_PAIRS.items():
        price = fetch_latest_price(pair)
        if price is not None:
            rates[currency] = price
        else:
            logger.warning(f"Using fallback FX rate for {currency}")
            rates[currency] = fallbacks[currency]

    return rates


def fetch_all_holdings(holdings_path: Path | None = None) -> dict[str, pd.DataFrame]:
    """
    Fetch price history for every ticker in holdings.json.

    Returns a dict mapping ticker → DataFrame.
    Tickers that fail are omitted with a warning.
    """
    if holdings_path is None:
        holdings_path = BASE_DIR / "config" / "holdings.json"

    with open(holdings_path) as f:
        holdings = json.load(f)

    all_tickers = (
        [h["ticker"] for h in holdings.get("equities", [])]
        + [h["ticker"] for h in holdings.get("etfs", [])]
        + [holdings["benchmark"]["ticker"]]
    )

    results: dict[str, pd.DataFrame] = {}
    for ticker in all_tickers:
        df = fetch_prices(ticker)
        if not df.empty:
            results[ticker] = df
        else:
            logger.warning(f"No data available for {ticker} — skipping")

    return results


def get_price_summary(ticker: str, lookback_days: int = 30) -> dict:
    """
    Return a human-readable price summary dict for a ticker.
    Used by analyst agents to build their context.

    Keys: ticker, latest_close, change_1d_pct, change_5d_pct,
          change_30d_pct, high_52w, low_52w, data_available
    """
    df = fetch_prices(ticker)
    if df.empty or "Close" not in df.columns:
        return {"ticker": ticker, "data_available": False}

    closes = df["Close"].dropna()
    if len(closes) < 2:
        return {"ticker": ticker, "data_available": False}

    latest = float(closes.iloc[-1])

    def pct_change(n_days: int) -> float | None:
        if len(closes) > n_days:
            return round((latest / float(closes.iloc[-n_days - 1]) - 1) * 100, 2)
        return None

    high_52w = float(closes.tail(252).max()) if len(closes) >= 252 else float(closes.max())
    low_52w = float(closes.tail(252).min()) if len(closes) >= 252 else float(closes.min())

    return {
        "ticker": ticker,
        "data_available": True,
        "latest_close": round(latest, 4),
        "change_1d_pct": pct_change(1),
        "change_5d_pct": pct_change(5),
        "change_30d_pct": pct_change(30),
        "high_52w": round(high_52w, 4),
        "low_52w": round(low_52w, 4),
        "pct_from_52w_high": round((latest / high_52w - 1) * 100, 2),
        "pct_from_52w_low": round((latest / low_52w - 1) * 100, 2),
    }
