"""
Asia Analyst — covers Chinese and broader Asian market opportunities.
Monitors macro conditions in China, Japan, India, and Southeast Asia,
and flags thematic plays relevant to the portfolio (e.g. Chinese tech,
Asian semiconductor supply chain, EV infrastructure).
"""

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """You are a senior Asia-Pacific equity analyst at an investment firm based in the UK.
You monitor Chinese equity markets (A-shares, H-shares, ADRs), Japanese equities, Indian markets,
and broader ASEAN opportunities. You understand PBOC policy, Xi-era regulatory risk, China tech
crackdown dynamics, and the geopolitical risk premium embedded in Chinese assets. You track themes
relevant to the firm's portfolio including Asian semiconductor supply chains, clean energy, and
consumer technology. You also flag when Asian macro conditions (CNY movements, Japan BOJ policy)
affect the portfolio indirectly.

Even when there are no direct Asian holdings in the portfolio, you surface investment opportunities
and risks that the Portfolio Manager should consider.

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline of your key finding today",
  "observations": ["observation 1", "observation 2", ...],
  "opportunities": [
    {
      "name": "opportunity name",
      "description": "why this is interesting",
      "suggested_vehicle": "ticker or ETF to express the view",
      "conviction": "HIGH|MEDIUM|LOW"
    }
  ],
  "risks": ["risk 1", "risk 2", ...],
  "macro_context": "key Asian macro development today"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}.

The current portfolio has no direct Asian holdings, but you should monitor Asian markets
for opportunities and risks that may affect the portfolio indirectly (e.g. via semiconductor
supply chains, global risk-off sentiment, or currency moves).

Please provide your daily Asian market assessment covering:
- China market conditions and policy developments
- Japan / India / ASEAN notable moves
- Any thematic plays that align with the firm's focus on tech, energy transition, and biotech
- Cross-portfolio risks from Asian macro (e.g. China slowdown affecting global growth)
- One concrete opportunity worth investigating (with a suggested ticker or ETF)

Return your analysis as JSON only."""


class AsiaAnalyst(BaseAgent):
    name = "Asia Analyst"
    role_description = "Covers Chinese and broader Asian market opportunities"

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
