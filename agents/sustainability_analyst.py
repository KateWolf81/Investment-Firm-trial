"""
Sustainability Analyst — covers ESG regulation, carbon markets, water, circular economy,
green finance, and biodiversity credits.  Flags ESG tail risks across the portfolio and
surfaces investment opportunities in sustainability themes.
"""

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """You are a senior sustainability and ESG analyst at an investment firm.
You track:

Regulatory:
- EU CSRD (Corporate Sustainability Reporting Directive) and SFDR (Sustainable Finance)
- UK SDR (Sustainability Disclosure Requirements)
- ISSB/IFRS S1 and S2 climate disclosure standards
- TNFD (Taskforce on Nature-related Financial Disclosures) — biodiversity

Carbon Markets:
- EU ETS (Emissions Trading System) carbon price
- UK ETS
- Voluntary carbon markets (VCMs) — Gold Standard, Verra/VCS
- Article 6 Paris Agreement — carbon credit cross-border transfers

Nature & Biodiversity:
- Biodiversity credits (emerging market)
- TNFD framework adoption
- Water scarcity investment thesis

Green Finance:
- Green bond issuance trends
- Transition finance instruments
- Blended finance for emerging markets

Circular Economy:
- Waste reduction regulation (EU Packaging Regulation)
- Extended producer responsibility schemes

Portfolio ESG Assessment:
- You flag ESG controversies or stranded asset risks in current holdings
- Nuclear energy (OKLO, SMR) — you treat this as a low-carbon transition technology
- PYC.AX — you note the ESG angle of rare disease therapeutics (positive social impact)
- AI/data centre holdings — you track energy intensity and water usage concerns

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline",
  "observations": ["observation 1", ...],
  "portfolio_esg_flags": [
    {
      "ticker": "TICKER",
      "flag_type": "RISK|OPPORTUNITY",
      "description": "what the flag is"
    }
  ],
  "carbon_market_update": "brief carbon price / VCM update",
  "regulatory_update": "most important ESG regulatory development today",
  "opportunities": [
    {
      "theme": "theme name",
      "description": "why it is compelling now",
      "suggested_vehicle": "ETF or direct holding"
    }
  ],
  "risks": ["risk 1", ...]
}"""

USER_PROMPT_TEMPLATE = """Today is {date}.

Current portfolio holdings for ESG assessment:
{holdings_summary}

Please provide your daily sustainability analysis. Cover:
- Any new ESG regulation (EU, UK, global) that affects the portfolio
- Carbon market price movements and what they signal
- Biodiversity / nature credits — any material developments
- Water scarcity — investment opportunities or portfolio risks
- ESG controversy screening across current holdings
- One actionable sustainability investment opportunity

Return your analysis as JSON only."""


class SustainabilityAnalyst(BaseAgent):
    name = "Sustainability Analyst"
    role_description = "ESG regulation, carbon markets, water, biodiversity, green finance"

    PORTFOLIO_TICKERS = [
        "PYC.AX", "BTR.AX", "OKLO", "SMR", "IONQ", "GOOGL", "NVDA",
        "SEMG.L", "AINF.L", "RBOT.L", "CNDX.L", "IITU.L",
    ]

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime

        holdings_lines = []
        for ticker in self.PORTFOLIO_TICKERS:
            if ticker in market_data and market_data[ticker].get("data_available"):
                d = market_data[ticker]
                holdings_lines.append(
                    f"  {ticker}: close={d.get('latest_close')} 30d={d.get('change_30d_pct')}%"
                )
            else:
                holdings_lines.append(f"  {ticker}: no data")

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
            holdings_summary="\n".join(holdings_lines),
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
