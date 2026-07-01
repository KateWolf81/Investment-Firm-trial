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


def _holdings_to_rows(holdings: dict) -> list[dict]:
    rows = []
    for kind in ("equities", "etfs"):
        for entry in holdings.get(kind, []):
            row = {c: entry.get(c, "") for c in COLUMNS}
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
        (etfs if row.get("type") == "etf" else equities).append(entry)
    return {"equities": equities, "etfs": etfs, "benchmark": benchmark}


current = load_holdings()

st.subheader("This week's holdings")
st.caption(
    "Edit tickers directly, or upload a CSV with the same columns below. Analysts route "
    "coverage automatically by sector/region/exchange, so new tickers just need those "
    "fields filled in reasonably."
)

uploaded = st.file_uploader("Upload a holdings CSV (optional)", type=["csv"])
if uploaded is not None:
    import pandas as pd
    upload_df = pd.read_csv(uploaded)
    for col in COLUMNS + ["type"]:
        if col not in upload_df.columns:
            upload_df[col] = ""
    st.session_state["holdings_rows"] = upload_df[COLUMNS + ["type"]].to_dict("records")

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
            "chg_this_week_pct": s.get("change_5d_pct") if s.get("data_available") else None,
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
    merged = dict(row)
    merged["price"] = p.get("price")
    merged["chg_this_week_pct"] = p.get("chg_this_week_pct")
    display_rows.append(merged)

DISPLAY_COLUMNS = ["ticker", "price", "chg_this_week_pct"] + [c for c in COLUMNS if c != "ticker"] + ["type"]

edited_df = st.data_editor(
    pd.DataFrame(display_rows, columns=DISPLAY_COLUMNS),
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "type": st.column_config.SelectboxColumn(options=["equity", "etf"]),
        "price": st.column_config.NumberColumn("Price", disabled=True, format="%.4f"),
        "chg_this_week_pct": st.column_config.NumberColumn("This Week", disabled=True, format="%+.2f%%"),
    },
    key="holdings_editor",
)
st.caption("Price / This Week are live from Yahoo Finance (cached 5 min) — not editable, and not saved to holdings.")

col1, col2 = st.columns([1, 4])
with col1:
    if st.button("💾 Save holdings", use_container_width=True):
        rows_to_save = edited_df[COLUMNS + ["type"]].to_dict("records")
        new_holdings = _rows_to_holdings(rows_to_save, current.get("benchmark", {}))
        save_holdings(new_holdings, HOLDINGS_FILE)
        st.session_state["holdings_rows"] = rows_to_save
        st.success(f"Saved {len(new_holdings['equities']) + len(new_holdings['etfs'])} holdings.")

st.divider()

st.subheader("Weekly briefing")
st.caption(
    "Runs all 8 analysts + Risk Manager + Portfolio Manager and produces the full weekly "
    "report. Takes a minute or two."
)

if st.button("🚀 Generate this week's briefing", type="primary"):
    with st.spinner("Running the firm — fetching prices, consulting analysts, synthesising..."):
        try:
            import main as firm_main
            report_path = firm_main.run_weekly_review(dry_run=True)
            st.session_state["last_report_path"] = str(report_path)
            st.success("Briefing generated.")
        except Exception as exc:
            st.error(f"Briefing generation failed: {exc}")

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
