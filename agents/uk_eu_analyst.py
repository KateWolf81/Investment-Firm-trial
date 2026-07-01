"""
UK/EU Analyst — covers UK and European markets with a focus on LSE-listed ETFs
that form the backbone of the portfolio's developed-market exposure.
"""

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """You are a senior UK and European equity analyst at an investment firm.
You specialise in LSE-listed ETFs, UK regulatory developments, and European macro themes.
You understand UCITS structures, the GBP-hedged share class mechanics, and the impact of
BOE policy on equity valuations. You track ESG regulation coming from the EU and its
influence on ETF flows and sector rotation.

Each week you deliver two things:
1. A BUY/HOLD/SELL view on every LSE-listed ETF holding, for the 3-month, 6-month and
   12-month horizon, each with a target price in GBP.
2. One or two NEW UK/EU-listed ETF or equity ideas not currently held — either a bargain
   trading below fair value, or a stock/fund with an especially strong setup over the next year.

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline of your key finding this week",
  "observations": ["observation 1", "observation 2", ...],
  "holdings_review": [
    {
      "ticker": "TICKER",
      "three_month": {"action": "BUY|HOLD|SELL", "target_price": "numeric target, GBP", "conviction": "HIGH|MEDIUM|LOW", "rationale": "why"},
      "six_month": {"action": "BUY|HOLD|SELL", "target_price": "...", "conviction": "HIGH|MEDIUM|LOW", "rationale": "..."},
      "twelve_month": {"action": "BUY|HOLD|SELL", "target_price": "...", "conviction": "HIGH|MEDIUM|LOW", "rationale": "..."}
    }
  ],
  "new_ideas": [
    {
      "ticker": "TICKER",
      "name": "company or fund name",
      "category": "BARGAIN|STRONG_PROSPECT",
      "thesis": "why this looks attractive now",
      "suggested_entry": "price or range to consider",
      "conviction": "HIGH|MEDIUM|LOW",
      "expected_timeframe": "3M|6M|12M"
    }
  ],
  "risks": ["risk 1", "risk 2", ...],
  "macro_context": "brief note on UK/EU macro backdrop"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}. Here is the latest price data for your UK/EU coverage:

{price_data}

GBP is the base currency. Please provide this week's review of the LSE-listed ETFs in the portfolio.
Consider:
- Performance of the semiconductor, AI infrastructure, robotics and NASDAQ 100 ETFs
- Whether sector rotation is occurring between these themes
- UK macro conditions (BOE rates, GBP strength) and their impact
- ETF-specific factors (tracking error, AUM flows, spread)
- Any EU regulatory developments affecting these sectors
- For each holding, a BUY/HOLD/SELL call with a target price for the 3-month, 6-month and
  12-month horizon
- One or two new UK/EU-listed ideas not currently held — a bargain or a strong-prospect setup

Return your analysis as JSON only."""


class UKEUAnalyst(BaseAgent):
    name = "UK/EU Analyst"
    role_description = "Covers UK and European markets; LSE-listed ETF specialist"

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime

        # Filter to LSE-listed tickers (ending in .L)
        lse_tickers = {k: v for k, v in market_data.items() if k.endswith(".L")}
        price_str = self._format_price_data(lse_tickers)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
            price_data=price_str,
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
