"""
Investment Firm Dashboard — one-page Streamlit app.

Lets you review/edit this week's holdings and generate the weekly briefing
with a single click, without needing a terminal or a fresh Claude Code session.

Run locally:   streamlit run dashboard/app.py
Deploy free:   share.streamlit.io — see dashboard/README.md
"""

import os
import re
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

def _extract_holdings_from_image(image_bytes: bytes, media_type: str) -> list[dict]:
    """Ask Claude to read holdings off a screenshot (brokerage app, statement, etc.)."""
    import base64
    import json
    import anthropic
    from config.settings import CLAUDE_MODEL

    client = anthropic.Anthropic()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    prompt = (
        "This is a screenshot of a stock/ETF portfolio (e.g. from a brokerage app or "
        "statement). Extract every holding you can see. For each one, capture:\n"
        "- ticker: the ticker symbol as shown (keep exchange suffixes like .AX or .L if visible)\n"
        "- name: the company/fund name if shown\n"
        "- shares_owned: number of shares/units, if shown\n"
        "- avg_cost: average cost per share/unit as a plain number (no currency symbol), if shown\n"
        "Omit any field you can't actually see — don't guess numbers. "
        "Respond with ONLY a JSON array, no other text, like:\n"
        '[{"ticker": "AAPL", "name": "Apple Inc", "shares_owned": 10, "avg_cost": 150.25}]'
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    raw = next((b.text for b in message.content if b.type == "text"), "[]")
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []


def _merge_extracted_holdings(rows: list[dict], extracted: list[dict]) -> list[dict]:
    """Update matching tickers in place (shares/cost only); append unseen ones as new rows."""
    by_ticker = {str(r.get("ticker", "")).strip().upper(): r for r in rows}
    for item in extracted:
        ticker = str(item.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        if ticker in by_ticker:
            if "shares_owned" in item:
                by_ticker[ticker]["shares_owned"] = item["shares_owned"]
            if "avg_cost" in item:
                by_ticker[ticker]["avg_cost"] = item["avg_cost"]
        else:
            new_row = {c: "" for c in COLUMNS}
            new_row["ticker"] = ticker
            new_row["name"] = item.get("name", "")
            new_row["shares_owned"] = item.get("shares_owned", 0) or 0
            new_row["avg_cost"] = item.get("avg_cost", 0) or 0
            new_row["type"] = "equity"
            rows.append(new_row)
            by_ticker[ticker] = new_row
    return rows


# Broker/statement CSV exports rarely use our exact column names — map common
# alternatives onto our schema instead of silently producing blank rows.
# Order matters within each list: the first alias present in the file wins.
CSV_COLUMN_ALIASES = {
    "ticker": ["ticker", "symbol", "code", "stock", "ticker_symbol"],
    "name": ["name", "company", "description", "security", "security_name", "company_name", "investment"],
    # Prefer the stock's own trading currency over the platform's reporting/base
    # currency — that's what matches the price data we fetch from the market.
    "currency": ["currency", "ccy", "market_currency", "valuation_currency"],
    "exchange": ["exchange", "market"],
    "sector": ["sector", "industry"],
    "region": ["region", "country"],
    "notes": ["notes", "note", "comment", "comments"],
    "shares_owned": ["shares_owned", "shares", "quantity", "qty", "units", "holding", "holdings", "share_qty"],
    "avg_cost": ["avg_cost", "average_cost", "avg_price", "average_price",
                 "purchase_price", "cost_per_share", "unit_cost"],
    # Total cost basis (not per-share) — some statements only give this; we divide
    # by shares_owned to get avg_cost when there's no direct per-share column.
    "cost_total": ["cost", "cost_basis", "book_cost", "total_cost"],
    "type": ["type", "asset_type", "asset_class", "instrument_type"],
}


def _normalize_col(col) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower()).strip("_")


def _clean_number(val) -> float:
    import pandas as pd
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^0-9.\-]", "", str(val))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0


def _import_csv(df) -> tuple[list[dict], set[str], bool]:
    """
    Map a CSV with arbitrary broker export column names onto our schema.

    Returns (rows, matched_columns, used_name_as_ticker). used_name_as_ticker is
    True when the file has no real ticker/symbol column, so the investment name
    was used as a placeholder — those rows need the ticker fixed manually.
    """
    import pandas as pd
    normalized = {_normalize_col(c): c for c in df.columns}
    mapping = {}
    for canon, aliases in CSV_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canon] = normalized[alias]
                break

    used_name_as_ticker = "ticker" not in mapping and "name" in mapping
    ticker_source = mapping.get("ticker") or (mapping.get("name") if used_name_as_ticker else None)

    rows = []
    for _, r in df.iterrows():
        raw = str(r[ticker_source]).strip() if ticker_source else ""
        if not raw or raw.lower() == "nan":
            continue
        row = {c: "" for c in COLUMNS}
        row["ticker"] = raw if used_name_as_ticker else raw.upper()
        for c in ("name", "currency", "exchange", "sector", "region", "notes"):
            if c in mapping:
                val = r[mapping[c]]
                row[c] = "" if pd.isna(val) else str(val).strip()
        shares = _clean_number(r[mapping["shares_owned"]]) if "shares_owned" in mapping else 0
        row["shares_owned"] = shares
        if "avg_cost" in mapping:
            row["avg_cost"] = _clean_number(r[mapping["avg_cost"]])
        elif "cost_total" in mapping and shares:
            row["avg_cost"] = round(_clean_number(r[mapping["cost_total"]]) / shares, 4)
        else:
            row["avg_cost"] = 0
        detected_type = str(r[mapping["type"]]).strip().lower() if "type" in mapping else ""
        row["type"] = detected_type if detected_type in ("equity", "etf") else "equity"
        rows.append(row)
    return rows, set(mapping.keys()), used_name_as_ticker


upload_tab1, upload_tab2 = st.tabs(["📄 Upload CSV", "📸 Upload screenshot"])

with upload_tab1:
    uploaded_csvs = st.file_uploader(
        "Upload one or more holdings CSVs", type=["csv"], accept_multiple_files=True, key="csv_uploader",
    )
    if uploaded_csvs:
        csv_sig = tuple((f.name, f.size) for f in uploaded_csvs)
        if st.session_state.get("_last_csv_sig") != csv_sig:
            import pandas as pd
            combined_rows = []
            any_placeholder_tickers = False
            for f in uploaded_csvs:
                df = pd.read_csv(f)
                file_rows, matched, used_name_as_ticker = _import_csv(df)
                combined_rows.extend(file_rows)
                if not matched or ("ticker" not in matched and "name" not in matched):
                    st.error(
                        f"**{f.name}**: couldn't find a ticker/symbol OR name column — got no "
                        f"holdings from this file. Its columns are: "
                        f"{', '.join(str(c) for c in df.columns)}. Rename a column to 'ticker' "
                        "or 'symbol' and re-upload."
                    )
                elif not file_rows:
                    st.warning(f"**{f.name}**: matched a column, but every row was empty.")
                elif used_name_as_ticker:
                    any_placeholder_tickers = True
            st.session_state["holdings_rows"] = combined_rows
            st.session_state["_last_csv_sig"] = csv_sig
            if combined_rows:
                st.success(f"Loaded {len(combined_rows)} holding(s) from {len(uploaded_csvs)} file(s).")
            if any_placeholder_tickers:
                st.warning(
                    "One or more files had no ticker/symbol column — only investment names. "
                    "I've put the name in the Ticker column as a placeholder for those rows; "
                    "please replace each with its real ticker (e.g. 'NVDA' for NVIDIA) in the "
                    "table below so prices and analysis work correctly."
                )

with upload_tab2:
    st.caption(
        "Upload one or more screenshots of your brokerage app or a statement — Claude reads "
        "off tickers, shares, and average cost where visible, as soon as you upload (no extra "
        "button needed). Review the table below afterwards; OCR from a screenshot isn't "
        "perfect, and fields it can't see (sector, exchange, region) will need to be filled "
        "in manually so analysts route coverage correctly."
    )
    screenshots = st.file_uploader(
        "Upload one or more screenshots", type=["png", "jpg", "jpeg"],
        accept_multiple_files=True, key="screenshot_uploader",
    )
    if screenshots:
        shot_sig = tuple((f.name, f.size) for f in screenshots)
        if st.session_state.get("_last_screenshot_sig") != shot_sig:
            with st.spinner(f"Reading {len(screenshots)} screenshot(s)..."):
                all_extracted, failures = [], []
                for f in screenshots:
                    try:
                        all_extracted.extend(_extract_holdings_from_image(f.getvalue(), f.type))
                    except Exception as exc:
                        failures.append(f"{f.name}: {exc}")
                st.session_state["_last_screenshot_sig"] = shot_sig
                if all_extracted:
                    base_rows = st.session_state.get("holdings_rows") or _holdings_to_rows(current)
                    st.session_state["holdings_rows"] = _merge_extracted_holdings(base_rows, all_extracted)
                    st.success(
                        f"Extracted {len(all_extracted)} holding(s) from {len(screenshots)} "
                        f"screenshot(s) — review them in the table below, then Save."
                    )
                elif not failures:
                    st.warning("Couldn't find any holdings in those images — try a clearer screenshot.")
                if failures:
                    st.error("Some screenshots couldn't be read: " + "; ".join(failures))

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
