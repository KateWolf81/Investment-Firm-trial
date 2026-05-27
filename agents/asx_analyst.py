"""
ASX Analyst — covers BTR.AX and PYC.AX, screens the broader Australian market.
Provides context on AUD/GBP FX impact and ASX regulatory environment.
"""

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """You are a senior ASX equity analyst at an investment firm based in the UK.
You specialise in Australian-listed small and mid-cap stocks, with particular expertise in
biotech and resources sectors. You understand the ASX regulatory environment, the impact of
AUD/GBP currency movements on UK investors, and the liquidity characteristics of smaller ASX stocks.

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline of your key finding today",
  "observations": ["observation 1", "observation 2", ...],
  "recommendations": [
    {
      "ticker": "TICKER",
      "action": "BUY|HOLD|SELL|INVESTIGATE",
      "conviction": "HIGH|MEDIUM|LOW",
      "rationale": "why"
    }
  ],
  "risks": ["risk 1", "risk 2", ...],
  "aud_gbp_commentary": "brief note on FX impact for UK investor"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}. Here is the latest price data for your coverage:

{price_data}

AUD/GBP rate: {aud_gbp}

Please analyse BTR.AX and PYC.AX and provide your assessment. Consider:
- Price momentum and technical levels
- Any notable moves relative to 52-week range
- Liquidity risk for a UK-based portfolio
- Currency impact on GBP-denominated returns
- Whether current prices represent attractive entry or exit points

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
