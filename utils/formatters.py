"""
Formatting helpers used across reports and console output.
"""


def fmt_gbp(amount: float) -> str:
    """£1,234.56"""
    return f"£{amount:,.2f}"


def fmt_pct(value: float, sign: bool = True) -> str:
    """±1.23%"""
    if sign:
        return f"{value:+.2f}%"
    return f"{value:.2f}%"


def fmt_shares(shares: float) -> str:
    """1,234 or 1,234.56 for fractional"""
    if shares == int(shares):
        return f"{int(shares):,}"
    return f"{shares:,.2f}"


def conviction_badge(conviction: str) -> str:
    """Returns a simple text badge for conviction level."""
    badges = {"HIGH": "[HIGH]", "MEDIUM": "[MED]", "LOW": "[LOW]"}
    return badges.get(conviction.upper(), f"[{conviction}]")


def action_badge(action: str) -> str:
    labels = {
        "BUY": "BUY ▲",
        "SELL": "SELL ▼",
        "HOLD": "HOLD —",
        "INVESTIGATE": "INVESTIGATE ?",
    }
    return labels.get(action.upper(), action)


def risk_level_badge(level: str) -> str:
    labels = {
        "LOW": "LOW",
        "MEDIUM": "MEDIUM",
        "HIGH": "HIGH ⚠",
        "CRITICAL": "CRITICAL !!",
    }
    return labels.get(level.upper(), level)
