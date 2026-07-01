"""
Holdings loader — single source of truth for the portfolio's tickers and metadata.

Analysts filter market_data using these helpers (by sector/exchange/region) instead
of hardcoding ticker lists, so replacing holdings.json — e.g. via a weekly upload —
is enough to redirect each analyst's coverage without touching their code.
"""

import json
from pathlib import Path

from config.settings import BASE_DIR

HOLDINGS_FILE = BASE_DIR / "config" / "holdings.json"


def load_holdings(path: Path | None = None) -> dict:
    with open(path or HOLDINGS_FILE) as f:
        return json.load(f)


def save_holdings(holdings: dict, path: Path | None = None) -> None:
    with open(path or HOLDINGS_FILE, "w") as f:
        json.dump(holdings, f, indent=2)


def all_entries(holdings: dict | None = None) -> list[dict]:
    """Every equity + ETF entry, each with ticker/name/currency/exchange/sector/region."""
    h = holdings if holdings is not None else load_holdings()
    return h.get("equities", []) + h.get("etfs", [])


def all_tickers(holdings: dict | None = None) -> list[str]:
    return [e["ticker"] for e in all_entries(holdings)]


def tickers_by_exchange(exchange: str, holdings: dict | None = None) -> list[str]:
    return [e["ticker"] for e in all_entries(holdings) if e.get("exchange") == exchange]


def tickers_by_sector(sectors: set[str], holdings: dict | None = None) -> list[str]:
    return [e["ticker"] for e in all_entries(holdings) if e.get("sector") in sectors]


def tickers_by_region(region: str, holdings: dict | None = None) -> list[str]:
    return [e["ticker"] for e in all_entries(holdings) if e.get("region") == region]
