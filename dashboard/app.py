"""
Investment Firm Dashboard — one-page Streamlit app.

Lets you review/edit this week's holdings and generate the weekly briefing
with a single click, without needing a terminal or a fresh Claude Code session.

Run locally:   streamlit run dashboard/app.py
Deploy free:   share.streamlit.io — see dashboard/README.md
"""

import os
import sys
from pathlib import Path

import streamlit as st

# Make the project root importable when Streamlit runs this file directly.
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# On Streamlit Community Cloud the API key lives in st.secrets, not a .env file.
# It must be in the environment *before* config.settings (and anything that
# imports it) is loaded for the first time. No secrets.toml locally is fine —
# st.secrets just behaves like an empty mapping in that case.
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass

from config.holdings import HOLDINGS_FILE, load_holdings, save_holdings  # noqa: E402

st.set_page_config(page_title="Investment Firm — Weekly Briefing", page_icon="📈", layout="wide")

st.title("📈 Investment Firm — Weekly Briefing")
st.caption("Paper portfolio simulation · not financial advice")

if not os.getenv("ANTHROPIC_API_KEY"):
    st.error(
        "ANTHROPIC_API_KEY is not set. Add it under **Settings → Secrets** if this app is "
        "deployed on Streamlit Community Cloud, or in a local `.env` file if running on your "
        "own machine."
    )
    st.stop()

COLUMNS = ["ticker", "name", "currency", "exchange", "sector", "region", "notes"]
POSITION_COLUMNS = ["shares_owned", "avg_cost"]  # your personal data, saved alongside each holding


def _holdings_to_rows(holdings: dict) -> list[dict]:
    rows = []
    for kind in ("equities", "etfs"):
        for entry in holdings.get(kind, []):
            row = {c: entry.get(c, "") for c in COLUMNS}
            row["shares_owned"] = entry.get("shares_owned", 0) or 0
            row["avg_cost"] = entry.get("avg_cost", 0) or 0
            row["type"] = "equity" if kind == "equities" else "etf"
            rows.append(row)
    return rows


def _rows_to_holdings(rows: list[dict], benchmark: dict) -> dict:
    equities, etfs = [], []
    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        entry = {c: row.get(c, "") for c in COLUMNS if row.get(c)}
        entry["ticker"] = ticker
        for c in POSITION_COLUMNS:
            val = row.get(c) or 0
            if val:
                entry[c] = val
        (etfs if row.get("type") == "etf" else equities).append(entry)
    return {"equities": equities, "etfs": etfs, "benchmark": benchmark}


current = load_holdings()

st.subheader("This week's holdings")
st.caption(
    "Edit tickers directly, or upload a CSV with the same columns below. Analysts route "
    "coverage automatically by sector/region/exchange, so new tickers just need those "
    "fields filled in reasonably. Fill in **Shares Owned** and **Avg Cost** (in the stock's "
    "own currency) to see your personal position value and gain."
)

uploaded = st.file_uploader("Upload a holdings CSV (optional)", type=["csv"])
if uploaded is not None:
    import pandas as pd
    upload_df = pd.read_csv(uploaded)
    for col in COLUMNS + POSITION_COLUMNS + ["type"]:
        if col not in upload_df.columns:
            upload_df[col] = 0 if col in POSITION_COLUMNS else ""
    st.session_state["holdings_rows"] = upload_df[COLUMNS + POSITION_COLUMNS + ["type"]].to_dict("records")

if "holdings_rows" not in st.session_state:
    st.session_state["holdings_rows"] = _holdings_to_rows(current)

import pandas as pd  # noqa: E402


@st.cache_data(ttl=300, show_spinner="Fetching live prices...")
def _fetch_price_snapshot(tickers: tuple) -> dict:
    from engine.market_data import get_price_summary
    snapshot = {}
    for ticker in tickers:
        s = get_price_summary(ticker)
        snapshot[ticker] = {
            "price": s.get("latest_close") if s.get("data_available") else None,
            "chg_today_pct": s.get("change_1d_pct") if s.get("data_available") else None,
            "chg_week_pct": s.get("change_5d_pct") if s.get("data_available") else None,
        }
    return snapshot


rows = st.session_state["holdings_rows"]
tickers = tuple(sorted({str(r.get("ticker", "")).strip().upper() for r in rows if r.get("ticker")}))

refresh_col, _ = st.columns([1, 5])
with refresh_col:
    if st.button("🔄 Refresh prices"):
        _fetch_price_snapshot.clear()

price_snapshot = _fetch_price_snapshot(tickers) if tickers else {}

display_rows = []
for row in rows:
    ticker = str(row.get("ticker", "")).strip().upper()
    p = price_snapshot.get(ticker, {})
    price = p.get("price")
    shares = float(row.get("shares_owned") or 0)
    avg_cost = float(row.get("avg_cost") or 0)

    merged = dict(row)
    merged["price"] = price
    merged["chg_today_pct"] = p.get("chg_today_pct")
    merged["chg_week_pct"] = p.get("chg_week_pct")
    merged["shares_owned"] = shares
    merged["avg_cost"] = avg_cost
    merged["market_value"] = (shares * price) if (price and shares) else None
    if price and avg_cost:
        merged["gain_pct"] = (price / avg_cost - 1) * 100
        merged["gain_value"] = shares * (price - avg_cost)
    else:
        merged["gain_pct"] = None
        merged["gain_value"] = None
    display_rows.append(merged)

DISPLAY_COLUMNS = (
    ["ticker", "price", "chg_today_pct", "chg_week_pct", "shares_owned", "avg_cost",
     "market_value", "gain_value", "gain_pct"]
    + [c for c in COLUMNS if c != "ticker"] + ["type"]
)

edited_df = st.data_editor(
    pd.DataFrame(display_rows, columns=DISPLAY_COLUMNS),
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "type": st.column_config.SelectboxColumn(options=["equity", "etf"]),
        "price": st.column_config.NumberColumn("Price", disabled=True, format="%.4f"),
        "chg_today_pct": st.column_config.NumberColumn("Today", disabled=True, format="%+.2f%%"),
        "chg_week_pct": st.column_config.NumberColumn("This Week", disabled=True, format="%+.2f%%"),
        "shares_owned": st.column_config.NumberColumn("Shares Owned", min_value=0.0, format="%.4f"),
        "avg_cost": st.column_config.NumberColumn("Avg Cost", min_value=0.0, format="%.4f"),
        "market_value": st.column_config.NumberColumn("Value", disabled=True, format="%.2f"),
        "gain_value": st.column_config.NumberColumn("Gain (£/$/etc)", disabled=True, format="%+.2f"),
        "gain_pct": st.column_config.NumberColumn("Gain %", disabled=True, format="%+.2f%%"),
    },
    key="holdings_editor",
)
st.caption(
    "Today / This Week = the stock's own price move (market performance). "
    "Value / Gain = your position, based on Shares Owned × Avg Cost you enter — shown in "
    "each stock's own currency, not converted to GBP. Price/Today/Week/Value/Gain are "
    "computed live and not saved; Shares Owned and Avg Cost ARE saved with your holdings."
)

col1, col2 = st.columns([1, 4])
with col1:
    if st.button("💾 Save holdings", use_container_width=True):
        rows_to_save = edited_df[COLUMNS + POSITION_COLUMNS + ["type"]].to_dict("records")
        new_holdings = _rows_to_holdings(rows_to_save, current.get("benchmark", {}))
        save_holdings(new_holdings, HOLDINGS_FILE)
        st.session_state["holdings_rows"] = rows_to_save
        st.success(f"Saved {len(new_holdings['equities']) + len(new_holdings['etfs'])} holdings.")

st.divider()

st.subheader("Weekly briefing")
st.caption(
    "Runs all 8 analysts + Risk Manager + Portfolio Manager, one after another — each makes "
    "its own call to Claude, so this genuinely takes 5-10 minutes. Leave the tab open; the "
    "report appears below the moment it's done. Closing the tab or restarting the app mid-run "
    "will interrupt it, so it's best to just wait."
)

if st.button("🚀 Generate this week's briefing", type="primary"):
    with st.spinner("Running the firm — fetching prices, consulting analysts, synthesising... this takes several minutes."):
        try:
            import main as firm_main
            report_path = firm_main.run_weekly_review(dry_run=True)
            st.session_state["last_report_path"] = str(report_path)
            st.success("Briefing generated.")
        except Exception as exc:
            st.error(f"Briefing generation failed: {exc}")

# If this session doesn't remember a report (e.g. after a reboot) but one was
# already generated, pick up the most recent file from disk instead of losing it.
if "last_report_path" not in st.session_state:
    from config.settings import REPORTS_DIR
    existing_reports = sorted(REPORTS_DIR.glob("briefing_*.html")) if REPORTS_DIR.exists() else []
    if existing_reports:
        st.session_state["last_report_path"] = str(existing_reports[-1])
        st.info(f"Showing the most recent previously-generated report ({existing_reports[-1].stem}).")

if "last_report_path" in st.session_state:
    report_path = Path(st.session_state["last_report_path"])
    if report_path.exists():
        html = report_path.read_text(encoding="utf-8")
        st.download_button(
            "⬇ Download this report",
            data=html,
            file_name=report_path.name,
            mime="text/html",
        )
        st.components.v1.html(html, height=2400, scrolling=True)
