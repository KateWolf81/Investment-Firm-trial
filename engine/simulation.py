"""
Paper trading simulation engine.

Manages the portfolio state stored in data/portfolio.json.
All monetary values are in GBP.  Non-GBP positions are converted at the
current FX rate when calculating NAV.

Positions dict structure (inside portfolio.json):
  {
    "OKLO": {
      "shares": 100,
      "avg_cost_local": 12.50,   # price paid, in the ticker's native currency
      "avg_cost_gbp": 9.87,      # price paid converted to GBP at time of purchase
      "currency": "USD",
      "last_price_local": 14.20,
      "last_price_gbp": 11.21,
      "market_value_gbp": 1121.0,
      "unrealised_pnl_gbp": 134.0
    },
    ...
  }
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from config.settings import PORTFOLIO_FILE, STARTING_CAPITAL_GBP
from engine.market_data import fetch_latest_price, fetch_fx_rates

logger = logging.getLogger(__name__)

Action = Literal["BUY", "SELL"]


# ── Portfolio I/O ──────────────────────────────────────────────────────────────

def load_portfolio() -> dict:
    """Load the portfolio JSON from disk.  Returns the initial state if missing."""
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return _initial_portfolio()


def save_portfolio(portfolio: dict) -> None:
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2)


def _initial_portfolio() -> dict:
    return {
        "meta": {
            "created": datetime.now().date().isoformat(),
            "base_currency": "GBP",
            "starting_capital": STARTING_CAPITAL_GBP,
        },
        "cash_gbp": STARTING_CAPITAL_GBP,
        "positions": {},
        "nav_history": [],
    }


# ── Order execution ────────────────────────────────────────────────────────────

def execute_order(
    ticker: str,
    action: Action,
    shares: float,
    currency: str,
    price_local: float | None = None,
    reason: str = "",
) -> dict:
    """
    Execute a paper trade and update portfolio.json.

    Parameters
    ----------
    ticker       : e.g. "OKLO"
    action       : "BUY" or "SELL"
    shares       : number of shares (can be fractional for ETFs)
    currency     : native currency of the instrument, e.g. "USD"
    price_local  : price in native currency; fetched live if not supplied
    reason       : short rationale string, written to the decision log

    Returns a result dict with keys: success, message, trade_value_gbp
    """
    portfolio = load_portfolio()
    fx = fetch_fx_rates()

    # Resolve live price if not provided
    if price_local is None:
        price_local = fetch_latest_price(ticker)
        if price_local is None:
            return {"success": False, "message": f"Could not fetch price for {ticker}"}

    fx_rate = fx.get(currency, 1.0) if currency != "GBP" else 1.0
    price_gbp = price_local * fx_rate
    trade_value_gbp = shares * price_gbp

    if action == "BUY":
        if portfolio["cash_gbp"] < trade_value_gbp:
            return {
                "success": False,
                "message": (
                    f"Insufficient cash: need £{trade_value_gbp:,.2f}, "
                    f"have £{portfolio['cash_gbp']:,.2f}"
                ),
            }
        _apply_buy(portfolio, ticker, shares, price_local, price_gbp, currency)
        portfolio["cash_gbp"] -= trade_value_gbp
        msg = f"BUY {shares} {ticker} @ {price_local:.4f} {currency} (£{price_gbp:.4f})"

    elif action == "SELL":
        result = _apply_sell(portfolio, ticker, shares, price_local, price_gbp, currency)
        if not result["success"]:
            return result
        portfolio["cash_gbp"] += trade_value_gbp
        msg = f"SELL {shares} {ticker} @ {price_local:.4f} {currency} (£{price_gbp:.4f})"

    else:
        return {"success": False, "message": f"Unknown action: {action}"}

    save_portfolio(portfolio)
    logger.info(msg)
    return {"success": True, "message": msg, "trade_value_gbp": trade_value_gbp}


def _apply_buy(
    portfolio: dict,
    ticker: str,
    shares: float,
    price_local: float,
    price_gbp: float,
    currency: str,
) -> None:
    pos = portfolio["positions"]
    if ticker in pos:
        # Update weighted average cost
        existing = pos[ticker]
        total_shares = existing["shares"] + shares
        existing["avg_cost_local"] = (
            (existing["avg_cost_local"] * existing["shares"] + price_local * shares)
            / total_shares
        )
        existing["avg_cost_gbp"] = (
            (existing["avg_cost_gbp"] * existing["shares"] + price_gbp * shares)
            / total_shares
        )
        existing["shares"] = total_shares
    else:
        pos[ticker] = {
            "shares": shares,
            "avg_cost_local": price_local,
            "avg_cost_gbp": price_gbp,
            "currency": currency,
            "last_price_local": price_local,
            "last_price_gbp": price_gbp,
            "market_value_gbp": shares * price_gbp,
            "unrealised_pnl_gbp": 0.0,
        }


def _apply_sell(
    portfolio: dict,
    ticker: str,
    shares: float,
    price_local: float,
    price_gbp: float,
    currency: str,
) -> dict:
    pos = portfolio["positions"]
    if ticker not in pos:
        return {"success": False, "message": f"No position in {ticker} to sell"}
    if pos[ticker]["shares"] < shares:
        return {
            "success": False,
            "message": (
                f"Cannot sell {shares} shares of {ticker} — "
                f"only {pos[ticker]['shares']} held"
            ),
        }
    pos[ticker]["shares"] -= shares
    if pos[ticker]["shares"] < 1e-6:
        del pos[ticker]
    return {"success": True}


# ── NAV calculation ────────────────────────────────────────────────────────────

def calculate_nav(portfolio: dict | None = None) -> dict:
    """
    Revalue all positions at current market prices and return a NAV snapshot.

    Returns
    -------
    dict with keys: nav_gbp, cash_gbp, positions_value_gbp, positions (updated),
                    date, pnl_gbp, pnl_pct
    """
    if portfolio is None:
        portfolio = load_portfolio()

    fx = fetch_fx_rates()
    positions_value = 0.0
    updated_positions = {}

    for ticker, pos in portfolio["positions"].items():
        currency = pos.get("currency", "GBP")
        price_local = fetch_latest_price(ticker)
        if price_local is None:
            # Keep last known value rather than crashing
            price_local = pos.get("last_price_local", pos["avg_cost_local"])

        fx_rate = fx.get(currency, 1.0) if currency != "GBP" else 1.0
        price_gbp = price_local * fx_rate
        market_value = pos["shares"] * price_gbp
        unrealised = (price_gbp - pos["avg_cost_gbp"]) * pos["shares"]

        updated_positions[ticker] = {
            **pos,
            "last_price_local": price_local,
            "last_price_gbp": price_gbp,
            "market_value_gbp": round(market_value, 2),
            "unrealised_pnl_gbp": round(unrealised, 2),
        }
        positions_value += market_value

    nav = portfolio["cash_gbp"] + positions_value
    starting = portfolio["meta"]["starting_capital"]
    pnl_gbp = nav - starting
    pnl_pct = (pnl_gbp / starting) * 100

    portfolio["positions"] = updated_positions
    save_portfolio(portfolio)

    return {
        "date": datetime.now().date().isoformat(),
        "nav_gbp": round(nav, 2),
        "cash_gbp": round(portfolio["cash_gbp"], 2),
        "positions_value_gbp": round(positions_value, 2),
        "positions": updated_positions,
        "pnl_gbp": round(pnl_gbp, 2),
        "pnl_pct": round(pnl_pct, 4),
    }


def record_nav_snapshot(nav_snapshot: dict) -> None:
    """Append today's NAV to the nav_history list in portfolio.json."""
    portfolio = load_portfolio()
    history = portfolio.setdefault("nav_history", [])
    today = nav_snapshot["date"]
    # Replace existing entry for today if present
    portfolio["nav_history"] = [h for h in history if h.get("date") != today]
    portfolio["nav_history"].append(nav_snapshot)
    save_portfolio(portfolio)
