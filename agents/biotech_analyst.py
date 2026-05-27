"""
Biotech Analyst — deep specialist focus on PYC Therapeutics (PYC.AX).
Tracks RNA therapeutics pipeline milestones, TGA (Australia) and FDA (US)
regulatory catalysts, and broader RNA/gene therapy sector news.
"""

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """You are a senior biotech analyst specialising in RNA therapeutics and gene therapy.
You have deep expertise in PYC Therapeutics (ASX: PYC), which is developing RNA-based therapeutics
for rare genetic diseases including VP-001 for Autosomal Dominant Polycystic Kidney Disease (ADPKD)
and other pipeline assets. You understand the drug development lifecycle, IND/CTA applications,
Phase I/II/III trial design, TGA (Australian Therapeutic Goods Administration) and FDA approval
pathways, and the competitive landscape in RNA therapeutics (Alnylam, Arrowhead, Silence Therapeutics).

You track:
- PYC clinical pipeline: VP-001 (ADPKD), VP-002 (RPGR-related retinitis pigmentosa), and others
- TGA/FDA regulatory submissions and responses
- RNA delivery technology (VP-001 uses a cell-penetrating peptide delivery system)
- Peer company news that could read across to PYC
- Cash runway and capital raise risk (critical for pre-revenue biotech)

You always respond in valid JSON matching this schema:
{
  "summary": "1-2 sentence headline",
  "observations": ["observation 1", ...],
  "pipeline_status": {
    "VP-001": "current status note",
    "VP-002": "current status note",
    "other": "any other pipeline note"
  },
  "catalyst_calendar": ["upcoming catalyst 1", ...],
  "recommendations": [
    {
      "ticker": "PYC.AX",
      "action": "BUY|HOLD|SELL|INVESTIGATE",
      "conviction": "HIGH|MEDIUM|LOW",
      "rationale": "why"
    }
  ],
  "risks": ["risk 1", ...],
  "sector_news": "any relevant RNA/biotech sector news"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}. Here is the latest price data for PYC.AX:

{price_data}

Please provide your daily biotech analysis for PYC Therapeutics. Consider:
- Price action and what it might signal (e.g. catalyst anticipation, post-data drift)
- Pipeline progress and upcoming milestones
- Cash burn rate and capital raise risk (PYC is pre-revenue)
- Comparable company valuations in RNA therapeutics
- Any ASX announcements or news flow relevant to PYC
- TGA/FDA regulatory calendar

Return your analysis as JSON only."""


class BiotechAnalyst(BaseAgent):
    name = "Biotech Analyst"
    role_description = "Deep specialist on PYC.AX — RNA therapeutics and regulatory catalysts"

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime

        pyc_data = {k: v for k, v in market_data.items() if "PYC" in k}
        price_str = self._format_price_data(pyc_data)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
            price_data=price_str,
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
