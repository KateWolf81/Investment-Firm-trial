"""
Risk dashboard — prints a formatted text risk summary to stdout.
Also used by the daily briefing HTML report for data.
"""

from utils.formatters import fmt_gbp, fmt_pct, risk_level_badge


def print_risk_dashboard(risk_report: dict) -> None:
    """Print a concise risk summary to the console."""
    quant = risk_report.get("quant_metrics", {})
    level = risk_report.get("overall_risk_level", "UNKNOWN")
    summary = risk_report.get("summary", "")

    print("\n" + "=" * 60)
    print("RISK DASHBOARD")
    print("=" * 60)
    print(f"Overall Risk:  {risk_level_badge(level)}")
    print(f"Summary:       {summary}")
    print()

    # Portfolio overview
    print(f"NAV:           {fmt_gbp(quant.get('nav_gbp', 0))}")
    print(f"Cash:          {fmt_gbp(quant.get('cash_gbp', 0))} ({quant.get('cash_pct', 0):.1f}%)")
    print(f"Speculative:   {quant.get('speculative_pct', 0):.1f}% of NAV (limit 30%)")
    print()

    # Concentrations
    concs = quant.get("concentrations", {})
    if concs:
        print("POSITION WEIGHTS:")
        for ticker, pct in sorted(concs.items(), key=lambda x: -x[1]):
            bar = "█" * int(pct / 2)
            flag = " ← BREACH" if pct > 10 else ""
            print(f"  {ticker:<12} {pct:>5.1f}%  {bar}{flag}")
        print()

    # FX
    fx = quant.get("fx_exposure", {})
    if fx:
        print("CURRENCY EXPOSURE:")
        for ccy, pct in sorted(fx.items()):
            flag = " ← BREACH" if pct > 60 else ""
            print(f"  {ccy:<6} {pct:>5.1f}%{flag}")
        print()

    # Drawdowns
    dds = quant.get("drawdowns", {})
    if dds:
        print("UNREALISED P&L BY POSITION:")
        for ticker, pct in sorted(dds.items(), key=lambda x: x[1]):
            sign = "+" if pct >= 0 else ""
            flag = " ← DRAWDOWN" if pct < -30 else ""
            print(f"  {ticker:<12} {sign}{pct:.1f}%{flag}")
        print()

    # Breaches
    breaches = risk_report.get("breaches", [])
    if breaches:
        print("⚠  BREACHES:")
        for b in breaches:
            print(f"  [{b['type']}] {b['ticker_or_currency']}: {b['current_value']} (limit {b['limit']})")
    else:
        print("✓  No risk limit breaches.")

    print("=" * 60 + "\n")
