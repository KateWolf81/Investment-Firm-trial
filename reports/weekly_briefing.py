"""
Weekly briefing report generator.

Takes all agent reports + portfolio state and renders the HTML briefing
to reports/output/briefing_YYYY-MM-DD.html.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config.settings import (
    REPORTS_DIR, TEMPLATES_DIR, STARTING_CAPITAL_GBP, BENCHMARK_TICKER,
    LAST_HOLDINGS_REVIEW_FILE,
)
from engine.benchmark import compare_to_benchmark
from engine.simulation import calculate_nav
from utils.formatters import fmt_gbp, fmt_pct

logger = logging.getLogger(__name__)

ACTION_RANK = {"SELL": 0, "HOLD": 1, "BUY": 2}


def generate_briefing(
    analyst_reports: dict[str, dict],
    pm_report: dict,
    risk_report: dict,
    market_data: dict | None = None,
) -> Path:
    """
    Render the weekly HTML briefing report.

    Parameters
    ----------
    analyst_reports : dict of agent_name → report dict (8 specialist analysts)
    pm_report       : Portfolio Manager's synthesised report
    risk_report     : Risk Manager's report
    market_data     : dict of ticker → price summary (for current price / weekly change)

    Returns the Path of the generated HTML file.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    market_data = market_data or {}

    today = datetime.now().date().isoformat()
    nav_snap = calculate_nav()
    bm_comparison = compare_to_benchmark(nav_snap["pnl_pct"])
    quant = risk_report.get("quant_metrics", {})

    weekly_summary = _build_weekly_summary(pm_report.get("holdings_review", []), market_data, today)

    # Build template context
    pnl_raw = nav_snap["pnl_pct"]
    alpha_raw = bm_comparison.get("alpha_pp")

    context = {
        "date": today,
        "generated_at": datetime.now().strftime("%H:%M UTC"),
        "benchmark_ticker": BENCHMARK_TICKER,

        # NAV bar
        "nav_gbp": fmt_gbp(nav_snap["nav_gbp"]),
        "starting_capital": fmt_gbp(STARTING_CAPITAL_GBP),
        "pnl_gbp": fmt_gbp(nav_snap["pnl_gbp"]),
        "pnl_pct": fmt_pct(pnl_raw),
        "pnl_class": "positive" if pnl_raw >= 0 else "negative",
        "cash_gbp": fmt_gbp(nav_snap["cash_gbp"]),
        "cash_pct": fmt_pct(quant.get("cash_pct", 100.0), sign=False),
        "alpha_pp": fmt_pct(alpha_raw) if alpha_raw is not None else "N/A",
        "alpha_class": "positive" if (alpha_raw or 0) >= 0 else "negative",
        "benchmark_return": fmt_pct(bm_comparison.get("return_pct", 0.0)),

        # PM report
        "pm_executive_summary": pm_report.get("executive_summary", ""),
        "pm_market_context": pm_report.get("market_context", ""),
        "pm_decisions": pm_report.get("decisions", []),
        "pm_holdings_review": pm_report.get("holdings_review", []),
        "pm_new_stock_recommendations": pm_report.get("new_stock_recommendations", []),
        "pm_watchlist": pm_report.get("watchlist", []),
        "pm_outlook": pm_report.get("outlook", ""),
        "weekly_summary": weekly_summary,

        # Holdings
        "positions": _format_positions(nav_snap["positions"], nav_snap["nav_gbp"]),

        # Risk
        "risk_level": risk_report.get("overall_risk_level", "UNKNOWN"),
        "risk_summary": risk_report.get("summary", ""),
        "risk_breaches": risk_report.get("breaches", []),
        "fx_exposure": quant.get("fx_exposure", {}),
        "speculative_pct": quant.get("speculative_pct", 0.0),

        # Analyst reports (list, ordered for display)
        "analyst_reports": list(analyst_reports.values()),
    }

    # Render
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("weekly_briefing.html")
    html = template.render(**context)

    output_path = REPORTS_DIR / f"briefing_{today}.html"
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"Weekly briefing written to {output_path}")
    return output_path


def _load_last_holdings_review() -> dict:
    """Return {ticker: {"action": ..., "target_price": ...}} from last week's run, or {}."""
    if not LAST_HOLDINGS_REVIEW_FILE.exists():
        return {}
    try:
        return json.loads(LAST_HOLDINGS_REVIEW_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not read last holdings review: {exc}")
        return {}


def _save_last_holdings_review(holdings_review: list[dict]) -> None:
    snapshot = {}
    for h in holdings_review:
        ticker = h.get("ticker")
        three_month = h.get("three_month", {})
        if ticker and isinstance(three_month, dict):
            snapshot[ticker] = {
                "action": three_month.get("action"),
                "target_price": three_month.get("target_price"),
            }
    LAST_HOLDINGS_REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_HOLDINGS_REVIEW_FILE.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _change_vs_last_week(ticker: str, current_action: str, previous: dict) -> str:
    prev = previous.get(ticker)
    if not prev or not prev.get("action"):
        return "New this week"

    prev_action = prev["action"]
    if prev_action == current_action:
        return f"Unchanged ({current_action})"

    prev_rank = ACTION_RANK.get(prev_action)
    curr_rank = ACTION_RANK.get(current_action)
    if prev_rank is None or curr_rank is None:
        return f"{prev_action} → {current_action}"
    arrow = "↑ Upgraded" if curr_rank > prev_rank else "↓ Downgraded"
    return f"{arrow}: {prev_action} → {current_action}"


def _build_weekly_summary(holdings_review: list[dict], market_data: dict, today: str) -> list[dict]:
    """
    One row per holding: current price, this-week's move, 3-month call, target price,
    change vs last week's call, and a one-line thesis. Persists this week's calls so
    next week's run can compute the same comparison.
    """
    previous = _load_last_holdings_review()
    rows = []
    for h in holdings_review:
        ticker = h.get("ticker", "?")
        three_month = h.get("three_month", {}) or {}
        action = three_month.get("action", "HOLD")
        price_summary = market_data.get(ticker, {})

        rows.append({
            "ticker": ticker,
            "current_price": price_summary.get("latest_close", "N/A") if price_summary.get("data_available") else "N/A",
            "change_this_week_pct": price_summary.get("change_5d_pct") if price_summary.get("data_available") else None,
            "action": action,
            "target_price": three_month.get("target_price", "N/A"),
            "vs_last_week": _change_vs_last_week(ticker, action, previous),
            "thesis": three_month.get("rationale", ""),
        })

    _save_last_holdings_review(holdings_review)
    return rows


def _format_positions(positions: dict, nav_gbp: float) -> list[dict]:
    rows = []
    for ticker, pos in positions.items():
        mv = pos.get("market_value_gbp", 0)
        weight_raw = (mv / nav_gbp * 100) if nav_gbp > 0 else 0
        rows.append({
            "ticker": ticker,
            "shares": f"{pos['shares']:,.2f}",
            "avg_cost_gbp": f"£{pos.get('avg_cost_gbp', 0):.4f}",
            "last_price_gbp": f"£{pos.get('last_price_gbp', 0):.4f}",
            "market_value_gbp": fmt_gbp(mv),
            "weight_pct": fmt_pct(weight_raw, sign=False),
            "weight_raw": round(weight_raw, 1),
            "unrealised_pnl": fmt_gbp(pos.get("unrealised_pnl_gbp", 0)),
            "pnl_raw": pos.get("unrealised_pnl_gbp", 0),
        })
    return sorted(rows, key=lambda x: -x["weight_raw"])
