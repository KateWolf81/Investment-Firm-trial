"""
Risk Manager — monitors the portfolio for concentration risk, currency exposure,
and position sizing breaches.  Does not call Claude for routine checks (pure Python),
but uses Claude to provide qualitative risk commentary on identified breaches.
"""

import logging
from datetime import datetime

from agents.base_agent import BaseAgent
from config.settings import MAX_SINGLE_POSITION_PCT, MAX_CURRENCY_EXPOSURE_PCT
from engine.market_data import fetch_fx_rates
from engine.simulation import load_portfolio, calculate_nav

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Risk Manager at an investment firm. You receive a structured
risk report from the quantitative risk system and provide qualitative commentary and
actionable recommendations to the Portfolio Manager.

You focus on:
- Concentration risk: any position exceeding 10% of portfolio NAV requires immediate attention
- Currency risk: AUD, USD, EUR, GBP exposures and FX tail risks
- Liquidity risk: small-cap ASX stocks (PYC.AX, BTR.AX) have limited daily volume
- Correlation risk: are multiple holdings all moving together in a risk-off event?
- Drawdown: flag if any position is down >30% from its average cost
- Speculative overweight: combined weight of pre-revenue companies (OKLO, SMR, IONQ, PYC, BTR)

You always respond in valid JSON matching this schema:
{
  "overall_risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "summary": "1-2 sentence risk headline",
  "breaches": [
    {
      "type": "CONCENTRATION|CURRENCY|LIQUIDITY|DRAWDOWN|SPECULATIVE_OVERWEIGHT",
      "ticker_or_currency": "affected item",
      "current_value": "e.g. 14.2%",
      "limit": "e.g. 10%",
      "action_required": "what the PM should do"
    }
  ],
  "observations": ["observation 1", ...],
  "recommendations": ["recommendation 1", ...]
}"""


class RiskManager(BaseAgent):
    name = "Risk Manager"
    role_description = "Monitors concentration, currency, drawdown, and position sizing"

    def analyse(self, market_data: dict) -> dict:
        # Step 1: compute quantitative risk metrics (no LLM needed)
        quant_report = self._compute_risk_metrics()

        # Step 2: pass the quant report to Claude for qualitative commentary
        user_prompt = f"""Today is {datetime.now().date().isoformat()}.

Here is the quantitative risk report for the portfolio:

Portfolio NAV: £{quant_report['nav_gbp']:,.2f}
Cash: £{quant_report['cash_gbp']:,.2f} ({quant_report['cash_pct']:.1f}% of NAV)

POSITION CONCENTRATIONS:
{self._format_concentrations(quant_report['concentrations'])}

CURRENCY EXPOSURES:
{self._format_fx_exposure(quant_report['fx_exposure'])}

POSITIONS IN DRAWDOWN:
{self._format_drawdowns(quant_report['drawdowns'])}

SPECULATIVE POSITION WEIGHT: {quant_report['speculative_pct']:.1f}%

BREACHES DETECTED:
{self._format_breaches(quant_report['breaches'])}

Please provide your risk assessment and recommendations for the Portfolio Manager.
Return your response as JSON only."""

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        report = self._base_report(parsed, raw)
        report["quant_metrics"] = quant_report
        return report

    # ── Quantitative risk calculations (pure Python, no LLM) ──────────────────

    def _compute_risk_metrics(self) -> dict:
        portfolio = load_portfolio()
        nav_snapshot = calculate_nav(portfolio)
        nav = nav_snapshot["nav_gbp"]
        cash = nav_snapshot["cash_gbp"]
        positions = nav_snapshot["positions"]

        concentrations = {}
        fx_exposure: dict[str, float] = {"GBP": cash}
        drawdowns = {}
        breaches = []

        SPECULATIVE = {"OKLO", "SMR", "IONQ", "PYC.AX", "BTR.AX"}
        speculative_value = 0.0

        fx_rates = fetch_fx_rates()

        for ticker, pos in positions.items():
            mv = pos["market_value_gbp"]
            weight = mv / nav if nav > 0 else 0.0
            concentrations[ticker] = round(weight * 100, 2)

            # FX exposure
            ccy = pos.get("currency", "GBP")
            fx_exposure[ccy] = fx_exposure.get(ccy, 0.0) + mv

            # Drawdown
            avg_cost_gbp = pos.get("avg_cost_gbp", 0)
            if avg_cost_gbp > 0:
                dd_pct = (pos["last_price_gbp"] / avg_cost_gbp - 1) * 100
                drawdowns[ticker] = round(dd_pct, 2)

            # Speculative weight
            if ticker in SPECULATIVE:
                speculative_value += mv

            # Concentration breach
            if weight > MAX_SINGLE_POSITION_PCT:
                breaches.append({
                    "type": "CONCENTRATION",
                    "ticker_or_currency": ticker,
                    "current_value": f"{weight*100:.1f}%",
                    "limit": f"{MAX_SINGLE_POSITION_PCT*100:.0f}%",
                })

            # Drawdown breach
            if ticker in drawdowns and drawdowns[ticker] < -30:
                breaches.append({
                    "type": "DRAWDOWN",
                    "ticker_or_currency": ticker,
                    "current_value": f"{drawdowns[ticker]:.1f}%",
                    "limit": "-30%",
                })

        # Currency concentration breaches
        for ccy, value in fx_exposure.items():
            ccy_pct = value / nav if nav > 0 else 0.0
            if ccy_pct > MAX_CURRENCY_EXPOSURE_PCT:
                breaches.append({
                    "type": "CURRENCY",
                    "ticker_or_currency": ccy,
                    "current_value": f"{ccy_pct*100:.1f}%",
                    "limit": f"{MAX_CURRENCY_EXPOSURE_PCT*100:.0f}%",
                })

        # Normalise FX exposure to percentages
        fx_exposure_pct = {
            ccy: round(val / nav * 100, 1) if nav > 0 else 0.0
            for ccy, val in fx_exposure.items()
        }

        return {
            "nav_gbp": nav,
            "cash_gbp": cash,
            "cash_pct": round(cash / nav * 100, 1) if nav > 0 else 100.0,
            "concentrations": concentrations,
            "fx_exposure": fx_exposure_pct,
            "drawdowns": drawdowns,
            "speculative_pct": round(speculative_value / nav * 100, 1) if nav > 0 else 0.0,
            "breaches": breaches,
        }

    def _format_concentrations(self, concs: dict) -> str:
        if not concs:
            return "  No positions held."
        lines = []
        for ticker, pct in sorted(concs.items(), key=lambda x: -x[1]):
            flag = " ⚠ BREACH" if pct > MAX_SINGLE_POSITION_PCT * 100 else ""
            lines.append(f"  {ticker}: {pct:.1f}%{flag}")
        return "\n".join(lines)

    def _format_fx_exposure(self, fx: dict) -> str:
        return "\n".join(f"  {ccy}: {pct:.1f}%" for ccy, pct in sorted(fx.items()))

    def _format_drawdowns(self, dds: dict) -> str:
        if not dds:
            return "  No open positions."
        return "\n".join(
            f"  {t}: {pct:+.1f}%" for t, pct in sorted(dds.items(), key=lambda x: x[1])
        )

    def _format_breaches(self, breaches: list) -> str:
        if not breaches:
            return "  None."
        return "\n".join(
            f"  [{b['type']}] {b['ticker_or_currency']}: "
            f"{b['current_value']} (limit {b['limit']})"
            for b in breaches
        )
