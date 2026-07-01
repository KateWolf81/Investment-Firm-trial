"""
ASX Analyst — covers BTR.AX and PYC.AX, screens the broader Australian market.
Provides context on AUD/GBP FX impact and ASX regulatory environment.
"""

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """You are a senior ASX equity analyst at an investment firm based in the UK.
You specialise in Australian-listed small and mid-cap stocks, with particular expertise in
biotech and resources sectors. You understand the ASX regulatory environment, the impact of
AUD/GBP currency movements on UK investors, and the liquidity characteristics of smaller ASX stocks.

Each week you deliver two things:
1. A BUY/HOLD/SELL view on every ASX holding in the portfolio, for the 3-month, 6-month and
   12-month horizon, each with a target price in the stock's local currency.
2. One or two NEW ASX stock ideas not currently held — either a bargain trading below fair
   value that you expect to re-rate, or a stock with an especially strong catalyst or growth
   setup over the next year.

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline of your key finding this week",
  "observations": ["observation 1", "observation 2", ...],
  "holdings_review": [
    {
      "ticker": "TICKER",
      "three_month": {"action": "BUY|HOLD|SELL", "target_price": "numeric target, local currency", "conviction": "HIGH|MEDIUM|LOW", "rationale": "why"},
      "six_month": {"action": "BUY|HOLD|SELL", "target_price": "...", "conviction": "HIGH|MEDIUM|LOW", "rationale": "..."},
      "twelve_month": {"action": "BUY|HOLD|SELL", "target_price": "...", "conviction": "HIGH|MEDIUM|LOW", "rationale": "..."}
    }
  ],
  "new_ideas": [
    {
      "ticker": "TICKER",
      "name": "company name",
      "category": "BARGAIN|STRONG_PROSPECT",
      "thesis": "why this looks attractive now",
      "suggested_entry": "price or range to consider",
      "conviction": "HIGH|MEDIUM|LOW",
      "expected_timeframe": "3M|6M|12M"
    }
  ],
  "risks": ["risk 1", "risk 2", ...],
  "aud_gbp_commentary": "brief note on FX impact for UK investor"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}. Here is the latest price data for your coverage:

{price_data}

AUD/GBP rate: {aud_gbp}

Please provide this week's ASX review of BTR.AX and PYC.AX. Consider:
- Price momentum and technical levels since last week
- Any notable moves relative to 52-week range
- Liquidity risk for a UK-based portfolio
- Currency impact on GBP-denominated returns
- For each holding, a BUY/HOLD/SELL call with a target price for the 3-month, 6-month and
  12-month horizon
- Screen the broader ASX market for one or two new ideas not currently held — a bargain stock
  set to re-rate, or one with an unusually strong near-term catalyst

Return your analysis as JSON only."""


class ASXAnalyst(BaseAgent):
    name = "ASX Analyst"
    role_description = "Covers BTR.AX and PYC.AX; screens Australian market"

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime
        from engine.market_data import fetch_fx_rates

        fx = fetch_fx_rates()
        aud_gbp = fx.get("AUD", "N/A")

        asx_tickers = {k: v for k, v in market_data.items() if k.endswith(".AX")}
        price_str = self._format_price_data(asx_tickers)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
            price_data=price_str,
            aud_gbp=f"{aud_gbp:.4f}" if isinstance(aud_gbp, float) else str(aud_gbp),
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
