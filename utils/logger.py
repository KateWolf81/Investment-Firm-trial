"""
Decision logger — appends every investment decision to data/decisions_log.jsonl.

Each line is a complete JSON object (JSONL format), making the log easy to:
- Read in a text editor
- Query with tools like jq
- Load into pandas for analysis
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from config.settings import DECISIONS_LOG_FILE

logger = logging.getLogger(__name__)


def log_decision(decision: dict, source: str = "unknown") -> None:
    """
    Append a single decision to the decisions log.

    Parameters
    ----------
    decision : dict — must contain at minimum 'ticker' and 'action'
    source   : which agent produced this decision
    """
    DECISIONS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().date().isoformat(),
        "source": source,
        **decision,
    }

    with open(DECISIONS_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    logger.debug(
        f"Logged decision: {decision.get('action','?')} {decision.get('ticker','?')} "
        f"from {source}"
    )


def log_agent_report(agent_name: str, report: dict) -> None:
    """Log a full agent report (without raw_response to keep log manageable)."""
    slim = {k: v for k, v in report.items() if k != "raw_response"}
    log_decision(slim, source=agent_name)


def load_decisions(
    date_filter: str | None = None,
    ticker_filter: str | None = None,
) -> list[dict]:
    """
    Load decisions from the log, with optional filtering.

    Parameters
    ----------
    date_filter   : ISO date string, e.g. "2026-05-27" — filter to a single day
    ticker_filter : e.g. "OKLO" — filter to a single ticker

    Returns list of decision dicts, newest first.
    """
    if not DECISIONS_LOG_FILE.exists():
        return []

    results = []
    with open(DECISIONS_LOG_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if date_filter and entry.get("date") != date_filter:
                    continue
                if ticker_filter and entry.get("ticker") != ticker_filter:
                    continue
                results.append(entry)
            except json.JSONDecodeError:
                continue

    return list(reversed(results))


def get_decision_summary(days: int = 7) -> dict:
    """Return a summary of decisions over the last N days."""
    from datetime import timedelta
    cutoff = (datetime.now().date() - timedelta(days=days)).isoformat()

    all_decisions = load_decisions()
    recent = [d for d in all_decisions if d.get("date", "") >= cutoff]

    summary: dict[str, dict] = {}
    for d in recent:
        ticker = d.get("ticker", "UNKNOWN")
        action = d.get("action", "?")
        if ticker not in summary:
            summary[ticker] = {"BUY": 0, "SELL": 0, "HOLD": 0, "INVESTIGATE": 0}
        summary[ticker][action] = summary[ticker].get(action, 0) + 1

    return {
        "period_days": days,
        "total_decisions": len(recent),
        "by_ticker": summary,
    }
