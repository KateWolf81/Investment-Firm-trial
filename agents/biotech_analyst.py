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

Each week you deliver two things:
1. A BUY/HOLD/SELL view on PYC.AX for the 3-month, 6-month and 12-month horizon, each with
   a target price in AUD.
2. One or two NEW RNA therapeutics / biotech ideas not currently held — either a bargain
   trading below fair value, or a stock with an especially strong catalyst or trial readout
   setup over the next year.

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
  "holdings_review": [
    {
      "ticker": "PYC.AX",
      "three_month": {"action": "BUY|HOLD|SELL", "target_price": "numeric target, AUD", "conviction": "HIGH|MEDIUM|LOW", "rationale": "why"},
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
  "risks": ["risk 1", ...],
  "sector_news": "any relevant RNA/biotech sector news"
}"""

USER_PROMPT_TEMPLATE = """Today is {date}. Here is the latest price data for PYC.AX:

{price_data}

Please provide this week's biotech review for PYC Therapeutics. Consider:
- Price action and what it might signal (e.g. catalyst anticipation, post-data drift)
- Pipeline progress and upcoming milestones
- Cash burn rate and capital raise risk (PYC is pre-revenue)
- Comparable company valuations in RNA therapeutics
- Any ASX announcements or news flow relevant to PYC
- TGA/FDA regulatory calendar
- A BUY/HOLD/SELL call with a target price for the 3-month, 6-month and 12-month horizon
- One or two new RNA/biotech ideas not currently held — a bargain or a strong-prospect setup

Return your analysis as JSON only."""


class BiotechAnalyst(BaseAgent):
    name = "Biotech Analyst"
    role_description = "Covers Biotech sector holdings — RNA therapeutics and regulatory catalysts"

    def analyse(self, market_data: dict) -> dict:
        from datetime import datetime
        from config.holdings import tickers_by_sector

        biotech_tickers = set(tickers_by_sector({"Biotech"}))
        biotech_data = {k: v for k, v in market_data.items() if k in biotech_tickers}
        price_str = self._format_price_data(biotech_data)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            date=datetime.now().date().isoformat(),
            price_data=price_str,
        )

        raw = self._call_claude(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json_response(raw)
        return self._base_report(parsed, raw)
