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

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline",
  "observations": ["observation 1", ...],
  "quantum_update": "brief IonQ-specific note",
  "ai_infrastructure_update": "AI/semiconductor theme note",
  "recommendations": [
    {
      "ticker": "TICKER",
      "action": "BUY|HOLD|SELL|INVESTIGATE",
      "conviction": "HIGH|MEDIUM|LOW",
      "rationale": "why"
    }
  ],
  "risks": ["risk 1", ...],
  "theme_momentum": "HIGH|MEDIUM|LOW"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}. Here is the latest price data for AI/quantum coverage:

{price_data}

Please provide your daily AI & quantum analysis. Consider:
- IonQ: any product announcements, partnership news, or quantum milestone updates
- AI infrastructure theme: data centre capex, hyperscaler spending guidance
- Semiconductor cycle: is SEMG tracking the broader chip cycle?
- Robotics: any notable automation contract wins or sector news
- Cross-holdings analysis: how does IONQ performance compare to NVDA/GOOGL as AI proxies?

Return your analysis as JSON only."""

AI_QUANTUM_TICKERS = {"IONQ", "AINF.L", "RBOT.L", "SEMG.L", "CNDX.L", "IITU.L", "NVDA", "GOOGL"}


class AIQuantumAnalyst(BaseAgent):
    name = "AI & Quantum Analyst"
    role_description = "Covers IONQ, robotics, AI infrastructure, and semiconductor ETFs"

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime

        relevant = {k: v for k, v in market_data.items() if k in AI_QUANTUM_TICKERS}
        price_str = self._format_price_data(relevant)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
            price_data=price_str,
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
