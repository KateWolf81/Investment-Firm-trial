"""
Base agent class.

Every analyst and the portfolio manager inherit from this.
It owns the Anthropic client and provides a single `_call_claude()` helper
that handles the API call, error handling, and response extraction.

Each subclass must implement `analyse(market_data)` which receives a dict
of price summaries and returns a structured report dict.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime

import anthropic

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all investment firm agents."""

    # Subclasses set these
    name: str = "BaseAgent"
    role_description: str = "Generic analyst"

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set.  "
                "Run: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = CLAUDE_MODEL

    @abstractmethod
    def analyse(self, market_data: dict) -> dict:
        """
        Run this agent's analysis.

        Parameters
        ----------
        market_data : dict mapping ticker → price_summary dict
                      (as returned by engine.market_data.get_price_summary)

        Returns
        -------
        dict with at minimum:
          agent       : str  (agent name)
          date        : str  (ISO date)
          summary     : str  (1-2 sentence headline)
          observations: list[str]
          holdings_review: list[dict]  one entry per covered holding, each with
                           ticker, three_month/six_month/twelve_month sub-dicts
                           (action, target_price, conviction, rationale)
          new_ideas   : list[dict]  new stock ideas not currently held, each with
                        ticker, name, category (BARGAIN|STRONG_PROSPECT), thesis,
                        suggested_entry, conviction, expected_timeframe
          risks       : list[str]
          raw_response: str  (full Claude output, for audit trail)
        """

    def _call_claude(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call Claude and return the text response.
        Raises on API errors so callers can decide how to handle failures.
        """
        logger.debug(f"[{self.name}] Calling {self.model}")
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text
        except anthropic.AuthenticationError:
            raise EnvironmentError("Invalid ANTHROPIC_API_KEY — check your key at console.anthropic.com")
        except anthropic.RateLimitError:
            raise RuntimeError("Anthropic rate limit hit — wait a moment and retry")
        except Exception as exc:
            logger.error(f"[{self.name}] Claude API error: {exc}")
            raise

    def _parse_json_response(self, raw: str) -> dict:
        """
        Extract a JSON block from Claude's response.
        Claude is instructed to return JSON; this extracts it robustly.
        """
        candidate = raw
        try:
            if "```json" in raw:
                start = raw.index("```json") + 7
                end = raw.index("```", start)
                candidate = raw[start:end].strip()
            elif "```" in raw:
                start = raw.index("```") + 3
                end = raw.index("```", start)
                candidate = raw[start:end].strip()
        except ValueError:
            # No proper closing fence — fall through and try parsing as-is
            candidate = raw

        # Strip any leading/trailing prose outside the JSON object
        brace = candidate.find("{")
        if brace > 0:
            candidate = candidate[brace:]

        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.warning(f"[{self.name}] Could not parse JSON response: {exc}")
            return {
                "summary": "Parse error — see raw_response",
                "observations": [],
                "recommendations": [],
                "risks": ["Could not parse agent response"],
            }

    def _base_report(self, parsed: dict, raw_response: str) -> dict:
        """Merge parsed JSON with standard envelope fields."""
        return {
            "agent": self.name,
            "date": datetime.now().date().isoformat(),
            "raw_response": raw_response,
            **parsed,
        }

    def _format_price_data(self, market_data: dict) -> str:
        """Convert market_data dict to a readable string for Claude's prompt."""
        lines = []
        for ticker, summary in market_data.items():
            if not summary.get("data_available", True):
                lines.append(f"  {ticker}: No price data available")
                continue
            lines.append(
                f"  {ticker}: close={summary.get('latest_close', 'N/A')}  "
                f"1d={summary.get('change_1d_pct', 'N/A')}%  "
                f"5d={summary.get('change_5d_pct', 'N/A')}%  "
                f"30d={summary.get('change_30d_pct', 'N/A')}%  "
                f"52w range={summary.get('low_52w', 'N/A')}–{summary.get('high_52w', 'N/A')}  "
                f"vs 52w high={summary.get('pct_from_52w_high', 'N/A')}%"
            )
        return "\n".join(lines)
