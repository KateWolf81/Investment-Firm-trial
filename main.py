"""
Investment Firm Simulation — main entry point.

Usage
-----
    # Run today's daily simulation (calls all agents, generates report)
    python main.py

    # Run in dry-run mode (no trades executed, just report)
    python main.py --dry-run

    # Run a 2-year backtest
    python main.py --backtest

    # Run just one analyst (useful for testing)
    python main.py --agent us_analyst
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Set up logging before any imports that might log at startup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def check_environment() -> bool:
    """Verify required environment variables are set before running."""
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n" + "=" * 60)
        print("ERROR: ANTHROPIC_API_KEY is not set.")
        print()
        print("To fix this:")
        print("  1. Get an API key at https://console.anthropic.com")
        print("  2. Run: export ANTHROPIC_API_KEY=sk-ant-...")
        print("  3. Then re-run: python main.py")
        print("=" * 60 + "\n")
        return False
    return True


def run_daily_simulation(dry_run: bool = True) -> None:
    """Run the full daily simulation — fetch data, run all agents, generate report."""
    from engine.market_data import fetch_all_holdings, get_price_summary
    from engine.simulation import calculate_nav, record_nav_snapshot
    from engine.benchmark import initialise_benchmark, compare_to_benchmark

    from agents.asx_analyst import ASXAnalyst
    from agents.uk_eu_analyst import UKEUAnalyst
    from agents.us_analyst import USAnalyst
    from agents.asia_analyst import AsiaAnalyst
    from agents.biotech_analyst import BiotechAnalyst
    from agents.nuclear_energy_analyst import NuclearEnergyAnalyst
    from agents.ai_quantum_analyst import AIQuantumAnalyst
    from agents.sustainability_analyst import SustainabilityAnalyst
    from agents.risk_manager import RiskManager
    from agents.portfolio_manager import PortfolioManager

    from reports.daily_briefing import generate_briefing
    from reports.risk_dashboard import print_risk_dashboard

    print(f"\n{'='*60}")
    print(f"INVESTMENT FIRM SIMULATION — {datetime.now().date()}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE PAPER TRADING'}")
    print(f"{'='*60}\n")

    # ── Step 1: Fetch market data ──────────────────────────────────────────────
    logger.info("Fetching market data for all holdings...")
    initialise_benchmark()

    all_data = fetch_all_holdings()
    market_data: dict = {}
    for ticker in _all_tickers():
        market_data[ticker] = get_price_summary(ticker)

    logger.info(f"Price data loaded for {sum(1 for v in market_data.values() if v.get('data_available'))} tickers")

    # ── Step 2: Run specialist analysts ───────────────────────────────────────
    analyst_agents = [
        ASXAnalyst(),
        UKEUAnalyst(),
        USAnalyst(),
        AsiaAnalyst(),
        BiotechAnalyst(),
        NuclearEnergyAnalyst(),
        AIQuantumAnalyst(),
        SustainabilityAnalyst(),
    ]

    analyst_reports: dict[str, dict] = {}
    for agent in analyst_agents:
        logger.info(f"Running {agent.name}...")
        try:
            report = agent.analyse(market_data)
            analyst_reports[agent.name] = report
            print(f"  ✓ {agent.name}: {report.get('summary', '')[:80]}")
        except Exception as exc:
            logger.error(f"{agent.name} failed: {exc}")
            analyst_reports[agent.name] = {
                "agent": agent.name,
                "date": datetime.now().date().isoformat(),
                "summary": f"Agent failed: {exc}",
                "observations": [],
                "recommendations": [],
                "risks": [str(exc)],
                "raw_response": "",
            }

    # ── Step 3: Risk Manager ───────────────────────────────────────────────────
    logger.info("Running Risk Manager...")
    risk_manager = RiskManager()
    try:
        risk_report = risk_manager.analyse(market_data)
        print(f"  ✓ Risk Manager: {risk_report.get('overall_risk_level', '?')} — {risk_report.get('summary', '')[:60]}")
    except Exception as exc:
        logger.error(f"Risk Manager failed: {exc}")
        risk_report = {
            "agent": "Risk Manager",
            "overall_risk_level": "UNKNOWN",
            "summary": f"Risk manager failed: {exc}",
            "breaches": [],
            "observations": [],
            "recommendations": [],
            "quant_metrics": {},
        }

    print_risk_dashboard(risk_report)

    # ── Step 4: Portfolio Manager ──────────────────────────────────────────────
    logger.info("Running Portfolio Manager...")
    pm = PortfolioManager()
    # Include risk report in the inputs to the PM
    all_reports = {**analyst_reports, "Risk Manager": risk_report}
    try:
        pm_report = pm.synthesise(all_reports, market_data)
        print(f"\n  ✓ Portfolio Manager: {pm_report.get('executive_summary', '')[:120]}")
    except Exception as exc:
        logger.error(f"Portfolio Manager failed: {exc}")
        pm_report = {
            "agent": "Portfolio Manager",
            "executive_summary": f"PM failed: {exc}",
            "decisions": [],
            "watchlist": [],
            "outlook": "",
        }

    # ── Step 5: Execute decisions (if not dry run) ────────────────────────────
    if not dry_run and pm_report.get("decisions"):
        nav_snap = calculate_nav()
        execution_results = pm.execute_decisions(
            pm_report["decisions"],
            nav_gbp=nav_snap["nav_gbp"],
            dry_run=False,
        )
        for r in execution_results:
            logger.info(f"Trade: {r}")
    else:
        logger.info("Dry run — no trades executed")

    # ── Step 6: Record NAV snapshot ────────────────────────────────────────────
    nav_snap = calculate_nav()
    bm = compare_to_benchmark(nav_snap["pnl_pct"])
    nav_snap["benchmark_return_pct"] = bm.get("return_pct")
    nav_snap["alpha_pp"] = bm.get("alpha_pp")
    record_nav_snapshot(nav_snap)

    # ── Step 7: Generate HTML report ──────────────────────────────────────────
    logger.info("Generating daily briefing report...")
    report_path = generate_briefing(analyst_reports, pm_report, risk_report)

    print(f"\n{'='*60}")
    print(f"Daily simulation complete.")
    print(f"Report: {report_path}")
    print(f"NAV:    £{nav_snap['nav_gbp']:,.2f} ({nav_snap['pnl_pct']:+.2f}%)")
    if bm.get("alpha_pp") is not None:
        print(f"Alpha:  {bm['alpha_pp']:+.2f}pp vs {bm['ticker']}")
    print(f"{'='*60}\n")


def run_single_agent(agent_name: str) -> None:
    """Run a single analyst agent for testing purposes."""
    from engine.market_data import get_price_summary

    agent_map = {
        "asx": "agents.asx_analyst.ASXAnalyst",
        "uk_eu": "agents.uk_eu_analyst.UKEUAnalyst",
        "us": "agents.us_analyst.USAnalyst",
        "asia": "agents.asia_analyst.AsiaAnalyst",
        "biotech": "agents.biotech_analyst.BiotechAnalyst",
        "nuclear": "agents.nuclear_energy_analyst.NuclearEnergyAnalyst",
        "ai_quantum": "agents.ai_quantum_analyst.AIQuantumAnalyst",
        "sustainability": "agents.sustainability_analyst.SustainabilityAnalyst",
        "risk": "agents.risk_manager.RiskManager",
        "pm": "agents.portfolio_manager.PortfolioManager",
    }

    if agent_name not in agent_map:
        print(f"Unknown agent '{agent_name}'. Available: {', '.join(agent_map.keys())}")
        sys.exit(1)

    module_path, class_name = agent_map[agent_name].rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    agent_class = getattr(module, class_name)
    agent = agent_class()

    market_data = {t: get_price_summary(t) for t in _all_tickers()}

    logger.info(f"Running {agent.name}...")
    report = agent.analyse(market_data)

    print(json.dumps({k: v for k, v in report.items() if k != "raw_response"}, indent=2))
    print(f"\n--- Raw Claude response ---\n{report.get('raw_response', '')}")


def run_backtest() -> None:
    """Run a 2-year buy-and-hold backtest."""
    from engine.backtester import run_backtest as _run_backtest
    from utils.formatters import fmt_pct

    print("\nRunning 2-year backtest...")
    results = _run_backtest(years=2)

    if "error" in results:
        print(f"Backtest failed: {results['error']}")
        return

    print(f"\nBacktest Results ({results['start_date']} → {results['end_date']})")
    print(f"Portfolio return:  {fmt_pct(results['portfolio_return_pct'])}")
    print(f"Benchmark return:  {fmt_pct(results['benchmark_return_pct'] or 0)}")
    print(f"Alpha:             {fmt_pct(results['alpha_pp'] or 0)} pp")
    print("\nIndividual position returns:")
    for ticker, ret in sorted(results["position_returns"].items(), key=lambda x: -x[1]):
        print(f"  {ticker:<12} {fmt_pct(ret)}")


def _all_tickers() -> list[str]:
    """Return all tracked tickers from holdings.json."""
    import json
    from config.settings import BASE_DIR
    with open(BASE_DIR / "config" / "holdings.json") as f:
        h = json.load(f)
    return (
        [x["ticker"] for x in h.get("equities", [])]
        + [x["ticker"] for x in h.get("etfs", [])]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Investment Firm Simulation")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Generate report without executing trades (default: True)")
    parser.add_argument("--live", action="store_true",
                        help="Execute paper trades (overrides --dry-run)")
    parser.add_argument("--backtest", action="store_true",
                        help="Run a 2-year buy-and-hold backtest")
    parser.add_argument("--agent", type=str,
                        help="Run a single agent by name (asx|uk_eu|us|asia|biotech|nuclear|ai_quantum|sustainability|risk|pm)")
    args = parser.parse_args()

    if not check_environment():
        sys.exit(1)

    if args.backtest:
        run_backtest()
    elif args.agent:
        run_single_agent(args.agent)
    else:
        dry_run = not args.live
        run_daily_simulation(dry_run=dry_run)
