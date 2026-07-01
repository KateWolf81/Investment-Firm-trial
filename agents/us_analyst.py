"""
US Analyst — covers Oklo (OKLO), NuScale (SMR), IonQ (IONQ), Alphabet (GOOGL),
Nvidia (NVDA), and US-focused ETFs.
"""

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """You are a senior US equity analyst at an investment firm based in the UK.
You cover a portfolio that includes small-cap nuclear energy companies (Oklo, NuScale),
a quantum computing pure-play (IonQ), mega-cap technology (Alphabet, Nvidia), and
US-focused technology ETFs. You understand the regulatory environment for nuclear SMRs
(NRC approval process), the competitive landscape in quantum computing, and the AI
infrastructure investment cycle. You always account for USD/GBP currency risk in your
analysis for UK-based investors.

Each week you deliver two things:
1. A BUY/HOLD/SELL view on every US holding in the portfolio, for the 3-month, 6-month and
   12-month horizon, each with a target price in USD.
2. One or two NEW US stock ideas not currently held — either a bargain trading below fair
   value that you expect to re-rate, or a stock with an especially strong catalyst or growth
   setup over the next year.

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline of your key finding this week",
  "observations": ["observation 1", "observation 2", ...],
  "holdings_review": [
    {
      "ticker": "TICKER",
      "three_month": {"action": "BUY|HOLD|SELL", "target_price": "numeric target, USD", "conviction": "HIGH|MEDIUM|LOW", "rationale": "why"},
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
  "usd_gbp_commentary": "brief note on currency impact for UK investor",
  "theme_outlook": "1-2 sentences on key US thematic trends"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}. Here is the latest price data for your US coverage:

{price_data}

USD/GBP rate: {usd_gbp}

Please provide this week's review of all US positions. Consider:
- Speculative positions (OKLO, SMR, IONQ): catalyst-driven, high volatility
- Large-cap tech (GOOGL, NVDA): earnings momentum, AI capex cycle
- US tech ETFs: sector rotation, index weights
- Fed policy and its effect on high-multiple growth stocks
- USD/GBP impact on GBP-denominated returns
- For each holding, a BUY/HOLD/SELL call with a target price for the 3-month, 6-month and
  12-month horizon
- One or two new US ideas not currently held — a bargain stock or one with an unusually
  strong near-term catalyst

Return your analysis as JSON only."""


class USAnalyst(BaseAgent):
    name = "US Analyst"
    role_description = "Covers US-region holdings (equities and US-focused ETFs)"

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime
        from engine.market_data import fetch_fx_rates
        from config.holdings import tickers_by_region

        fx = fetch_fx_rates()
        usd_gbp = fx.get("USD", "N/A")

        us_tickers = set(tickers_by_region("US"))
        us_data = {k: v for k, v in market_data.items() if k in us_tickers}
        price_str = self._format_price_data(us_data)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
            price_data=price_str,
            usd_gbp=f"{usd_gbp:.4f}" if isinstance(usd_gbp, float) else str(usd_gbp),
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
