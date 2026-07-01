"""
Portfolio Manager — the senior decision-maker.

Receives structured reports from all 8 specialist analysts plus the Risk Manager,
synthesises them into a weekly briefing covering a 3/6/12-month BUY/HOLD/SELL view
on every holding (with target prices) plus a consolidated list of new stock ideas.

The PM is also responsible for executing approved trades via the simulation engine.
"""

import json
import logging
from datetime import datetime

from agents.base_agent import BaseAgent
from engine.simulation import execute_order
from utils.logger import log_decision

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Portfolio Manager of a UK-based investment firm managing a £100,000
paper portfolio. You receive weekly reports from 8 specialist analysts and a Risk Manager, and you
are responsible for synthesising them into the firm's weekly briefing and making final investment
decisions.

Your investment mandate:
- Base currency: GBP
- Universe: ASX biotech/resources, UK/EU ETFs, US tech/nuclear/quantum, Asian opportunities
- Risk limit: no single position >10% of NAV
- Speculative positions (pre-revenue companies) should not exceed 30% of portfolio combined
- Maintain diversification across themes: biotech, nuclear energy, AI/quantum, sustainability

Your decision framework:
1. Weigh analyst conviction levels and identify consensus views
2. Check risk manager flags — any CRITICAL or CONCENTRATION breach must be addressed first
3. Consider portfolio-level themes vs individual stock stories
4. Size positions proportionally to conviction and liquidity
5. For every current holding, reconcile the covering analyst's 3/6/12-month BUY/HOLD/SELL
   calls and target prices into one consolidated view
6. Review every analyst's "new_ideas" submissions and select the strongest few — bargains
   set to re-rate, or stocks with an especially strong prospect — for the weekly recommendation list

You always respond in valid JSON matching this schema:
{
  "executive_summary": "3-5 sentence portfolio overview for this week",
  "market_context": "brief global market backdrop",
  "holdings_review": [
    {
      "ticker": "TICKER",
      "three_month": {"action": "BUY|HOLD|SELL", "target_price": "numeric target, local currency", "rationale": "consolidated reasoning"},
      "six_month": {"action": "BUY|HOLD|SELL", "target_price": "...", "rationale": "..."},
      "twelve_month": {"action": "BUY|HOLD|SELL", "target_price": "...", "rationale": "..."},
      "supporting_analysts": ["Analyst Name 1", "Analyst Name 2"]
    }
  ],
  "new_stock_recommendations": [
    {
      "ticker": "TICKER",
      "name": "company or fund name",
      "category": "BARGAIN|STRONG_PROSPECT",
      "conviction": "HIGH|MEDIUM|LOW",
      "rationale": "why this made the cut",
      "suggested_entry": "price or range to consider",
      "expected_timeframe": "3M|6M|12M",
      "source_analyst": "Analyst Name"
    }
  ],
  "decisions": [
    {
      "ticker": "TICKER",
      "action": "BUY|SELL|HOLD|INVESTIGATE",
      "size_pct_of_nav": 2.5,
      "conviction": "HIGH|MEDIUM|LOW",
      "rationale": "detailed reasoning referencing analyst inputs",
      "supporting_analysts": ["Analyst Name 1", "Analyst Name 2"],
      "key_risk": "main risk to this decision"
    }
  ],
  "portfolio_changes_summary": "what is changing this week and why",
  "watchlist": ["TICKER1 — reason to watch", ...],
  "outlook": "portfolio outlook for the next 4-6 weeks"
}"""


class PortfolioManager(BaseAgent):
    name = "Portfolio Manager"
    role_description = "Synthesises all analyst reports into daily decisions"

    def analyse(self, market_data: dict) -> dict:
        """
        This override is not normally called directly.
        Use synthesise() which accepts analyst reports.
        """
        return self.synthesise({}, market_data)

    def synthesise(self, analyst_reports: dict[str, dict], market_data: dict) -> dict:
        """
        Main entry point for the Portfolio Manager.

        Parameters
        ----------
        analyst_reports : dict mapping agent name → their report dict
        market_data     : dict mapping ticker → price_summary

        Returns a full PM decision report.
        """
        nav_summary = self._get_nav_summary()
        reports_text = self._format_analyst_reports(analyst_reports)
        price_text = self._format_price_data(market_data)

        user_prompt = f"""Today is {datetime.now().date().isoformat()}.

PORTFOLIO STATUS:
{nav_summary}

CURRENT PRICES:
{price_text}

ANALYST REPORTS:
{reports_text}

Based on all analyst inputs, please produce this week's briefing.
Focus especially on:
1. Any risk manager breaches that require immediate action
2. Consolidating each holding's 3/6/12-month BUY/HOLD/SELL view and target price from the
   covering analyst(s) into "holdings_review"
3. Selecting the strongest new stock ideas across all analysts' "new_ideas" submissions into
   "new_stock_recommendations" — prioritise multi-analyst consensus and clear bargains or
   strong-prospect setups
4. High-conviction analyst recommendations with multiple analyst support
5. Rebalancing opportunities if the portfolio is drifting from target weights

Return your briefing as JSON only."""

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        report = self._base_report(parsed, raw)

        # Log all decisions to the decisions log
        for decision in parsed.get("decisions", []):
            log_decision(decision, source="PortfolioManager")

        return report

    def execute_decisions(self, decisions: list[dict], nav_gbp: float, dry_run: bool = True) -> list[dict]:
        """
        Execute the PM's decisions as paper trades.

        Parameters
        ----------
        decisions : list of decision dicts from synthesise()
        nav_gbp   : current portfolio NAV in GBP (used to size positions)
        dry_run   : if True, log what would happen but don't execute trades

        Returns list of execution result dicts.
        """
        from config.holdings import load_holdings
        results = []

        for d in decisions:
            action = d.get("action", "HOLD")
            ticker = d.get("ticker")
            size_pct = d.get("size_pct_of_nav", 0)

            if action not in ("BUY", "SELL") or not ticker or size_pct <= 0:
                continue

            trade_value_gbp = nav_gbp * (size_pct / 100)

            if dry_run:
                results.append({
                    "ticker": ticker,
                    "action": action,
                    "trade_value_gbp": round(trade_value_gbp, 2),
                    "status": "DRY_RUN — not executed",
                    "rationale": d.get("rationale", ""),
                })
                logger.info(
                    f"[DRY RUN] {action} £{trade_value_gbp:,.2f} of {ticker}"
                )
            else:
                # Look up currency for the ticker
                from engine.market_data import fetch_latest_price, fetch_fx_rates
                price = fetch_latest_price(ticker)
                fx = fetch_fx_rates()

                currency = _resolve_currency(ticker)
                fx_rate = fx.get(currency, 1.0) if currency != "GBP" else 1.0
                price_gbp = price * fx_rate if price else 0

                if price_gbp > 0:
                    shares = trade_value_gbp / price_gbp
                    result = execute_order(
                        ticker=ticker,
                        action=action,
                        shares=shares,
                        currency=currency,
                        price_local=price,
                        reason=d.get("rationale", "PM decision"),
                    )
                    results.append(result)
                else:
                    results.append({
                        "ticker": ticker,
                        "action": action,
                        "status": "FAILED — could not fetch price",
                    })

        return results

    def _get_nav_summary(self) -> str:
        try:
            from engine.simulation import calculate_nav
            snap = calculate_nav()
            lines = [
                f"NAV: £{snap['nav_gbp']:,.2f}",
                f"Cash: £{snap['cash_gbp']:,.2f}",
                f"Positions value: £{snap['positions_value_gbp']:,.2f}",
                f"P&L: £{snap['pnl_gbp']:+,.2f} ({snap['pnl_pct']:+.2f}%)",
            ]
            if snap["positions"]:
                lines.append("Current positions:")
                for ticker, pos in snap["positions"].items():
                    lines.append(
                        f"  {ticker}: {pos['shares']:.2f} shares @ "
                        f"£{pos['last_price_gbp']:.4f} = £{pos['market_value_gbp']:,.2f} "
                        f"(P&L: £{pos['unrealised_pnl_gbp']:+,.2f})"
                    )
            else:
                lines.append("No open positions — fully in cash.")
            return "\n".join(lines)
        except Exception as exc:
            return f"NAV unavailable: {exc}"

    def _format_analyst_reports(self, reports: dict[str, dict]) -> str:
        if not reports:
            return "No analyst reports received."
        sections = []
        for agent_name, report in reports.items():
            sections.append(f"--- {agent_name.upper()} ---")
            sections.append(f"Summary: {report.get('summary', 'N/A')}")

            holdings = report.get("holdings_review", [])
            if holdings:
                sections.append("Holdings review (3m / 6m / 12m):")
                for h in holdings:
                    if not isinstance(h, dict):
                        continue
                    ticker = h.get("ticker", "?")
                    horizons = []
                    for key, label in (("three_month", "3M"), ("six_month", "6M"), ("twelve_month", "12M")):
                        horizon = h.get(key, {})
                        if isinstance(horizon, dict):
                            horizons.append(
                                f"{label}: {horizon.get('action','?')} "
                                f"@ {horizon.get('target_price','?')} "
                                f"[{horizon.get('conviction','?')}] — {horizon.get('rationale','')}"
                            )
                    sections.append(f"  {ticker}: " + " | ".join(horizons))

            ideas = report.get("new_ideas", [])
            if ideas:
                sections.append("New ideas:")
                for i in ideas:
                    if isinstance(i, dict):
                        sections.append(
                            f"  {i.get('ticker','?')} ({i.get('name','')}) — {i.get('category','?')} "
                            f"[{i.get('conviction','?')}], entry {i.get('suggested_entry','?')}, "
                            f"{i.get('expected_timeframe','?')}: {i.get('thesis','')}"
                        )
                    else:
                        sections.append(f"  {i}")

            risks = report.get("risks", [])
            if risks:
                sections.append(f"Key risks: {'; '.join(risks[:3])}")
            sections.append("")
        return "\n".join(sections)


def _resolve_currency(ticker: str) -> str:
    """Infer the native currency from the ticker suffix."""
    if ticker.endswith(".AX"):
        return "AUD"
    if ticker.endswith(".L"):
        return "GBP"
    if ticker.endswith(".PA") or ticker.endswith(".DE") or ticker.endswith(".AS"):
        return "EUR"
    return "USD"  # default for NYSE/NASDAQ
