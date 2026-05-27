"""
Global configuration for the investment firm simulation.
All tuneable parameters live here so nothing is scattered through the codebase.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent

# Load .env file if present — safe to call even if the file doesn't exist
load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
HISTORICAL_DIR = DATA_DIR / "historical"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
DECISIONS_LOG_FILE = DATA_DIR / "decisions_log.jsonl"
REPORTS_DIR = BASE_DIR / "reports" / "output"
TEMPLATES_DIR = BASE_DIR / "templates"

# ── Anthropic ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── Portfolio ──────────────────────────────────────────────────────────────────
STARTING_CAPITAL_GBP = 100_000.0
BASE_CURRENCY = "GBP"
BENCHMARK_TICKER = "IWDA.L"

# ── Risk limits ────────────────────────────────────────────────────────────────
# Risk Manager will flag any position that exceeds this share of total portfolio NAV
MAX_SINGLE_POSITION_PCT = 0.10  # 10 %

# Warn if combined exposure to a single currency exceeds this
MAX_CURRENCY_EXPOSURE_PCT = 0.60  # 60 %

# ── Backtesting ────────────────────────────────────────────────────────────────
BACKTEST_YEARS = 2
