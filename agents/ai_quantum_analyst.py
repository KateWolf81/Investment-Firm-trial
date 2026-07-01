"""
AI & Quantum Analyst — covers IonQ (IONQ), robotics ETFs, and AI infrastructure ETFs.
Tracks quantum computing milestones, AI capex cycle, and semiconductor supply chain.
"""

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """You are a senior technology analyst specialising in quantum computing,
artificial intelligence infrastructure, and robotics/automation. You cover:

- IonQ (NYSE: IONQ): trapped-ion quantum computing, targeting algorithmic qubits milestone.
  Pre-revenue at scale, but has commercial cloud contracts with AWS, Azure, Google Cloud.
  Key metrics: algorithmic qubits (#AQ), quantum volume, error rates.

- AI Infrastructure ETFs (AINF.L): exposure to data centres, power infrastructure,
  networking equipment, and cooling systems supporting AI workloads.

- Robotics ETFs (RBOT.L): factory automation, collaborative robots, autonomous vehicles,
  industrial AI.

- Semiconductor ETFs (SEMG.L): full semiconductor supply chain — design (NVDA, ASML),
  fabrication (TSMC), equipment, materials.

- NASDAQ 100 ETF (CNDX.L): broad US tech exposure, heavily weighted to Magnificent 7.

- S&P 500 IT Sector ETF (IITU.L): US information technology sector.

You understand:
- Quantum computing competitive landscape (IBM, Google, IonQ, Quantinuum, PsiQuantum)
- AI model training vs inference infrastructure investment
- Semiconductor cycle dynamics (inventory corrections, capacity expansions)
- Robotics adoption curves in manufacturing and logistics

Each week you deliver two things:
1. A BUY/HOLD/SELL view on every holding in your coverage, for the 3-month, 6-month and
   12-month horizon, each with a target price.
2. One or two NEW AI/quantum/robotics ideas not currently held — either a bargain trading
   below fair value, or a stock/ETF with an especially strong catalyst or growth setup over
   the next year.

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline",
  "observations": ["observation 1", ...],
  "quantum_update": "brief IonQ-specific note",
  "ai_infrastructure_update": "AI/semiconductor theme note",
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
      "name": "company or fund name",
      "category": "BARGAIN|STRONG_PROSPECT",
      "thesis": "why this looks attractive now",
      "suggested_entry": "price or range to consider",
      "conviction": "HIGH|MEDIUM|LOW",
      "expected_timeframe": "3M|6M|12M"
    }
  ],
  "risks": ["risk 1", ...],
  "theme_momentum": "HIGH|MEDIUM|LOW"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}. Here is the latest price data for AI/quantum coverage:

{price_data}

Please provide this week's AI & quantum review. Consider:
- IonQ: any product announcements, partnership news, or quantum milestone updates
- AI infrastructure theme: data centre capex, hyperscaler spending guidance
- Semiconductor cycle: is SEMG tracking the broader chip cycle?
- Robotics: any notable automation contract wins or sector news
- Cross-holdings analysis: how does IONQ performance compare to NVDA/GOOGL as AI proxies?
- For each holding, a BUY/HOLD/SELL call with a target price for the 3-month, 6-month and
  12-month horizon
- One or two new ideas not currently held — a bargain or a strong-prospect setup

Return your analysis as JSON only."""

AI_QUANTUM_SECTORS = {"Quantum Computing", "AI Infrastructure", "Robotics", "Semiconductors", "Technology"}


class AIQuantumAnalyst(BaseAgent):
    name = "AI & Quantum Analyst"
    role_description = "Covers quantum computing, robotics, AI infrastructure, semiconductor and technology holdings"

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime
        from config.holdings import tickers_by_sector

        ai_quantum_tickers = set(tickers_by_sector(AI_QUANTUM_SECTORS))
        relevant = {k: v for k, v in market_data.items() if k in ai_quantum_tickers}
        price_str = self._format_price_data(relevant)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
            price_data=price_str,
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
