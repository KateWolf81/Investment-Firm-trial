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
    "Edit tickers directly below, or upload a CSV/screenshot in any format — you'll "
    "confirm which column is which, nothing is guessed silently. In the table, "
    "📄 columns are your data (edited or uploaded); 🌐 columns are fetched live from "
    "Yahoo Finance. Analysts route coverage automatically by sector/region/exchange, "
    "so new tickers just need those fields filled in reasonably."
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


NONE_OPTION = "-- none --"


def _safe_read_csv(uploaded_file) -> tuple:
    """
    Read a CSV robustly, guarding against pandas' worst CSV footgun: if any row has
    MORE fields than the header (usually an unquoted comma inside a value — a name,
    or a number like "11,845.02"), pandas silently assumes the file has an implicit
    index column and shifts EVERY row's values one column to the left — no error,
    just quietly wrong data throughout the whole file. `index_col=False` disables
    that assumption; the offending row still loses its extra field, but every other
    row (and every other column) stays correctly aligned.
    """
    import pandas as pd
    import warnings
    from io import StringIO
    text = uploaded_file.getvalue().decode("utf-8", errors="replace")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = pd.read_csv(StringIO(text), index_col=False)
        had_ragged_rows = any(issubclass(w.category, pd.errors.ParserWarning) for w in caught)
    return df, had_ragged_rows


def _guess_column_mapping(df) -> dict:
    """Best-effort default selections for the manual mapping UI below — never used silently."""
    normalized = {_normalize_col(c): c for c in df.columns}
    mapping = {}
    for canon, aliases in CSV_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canon] = normalized[alias]
                break
    return mapping


def _build_rows_from_mapping(df, ticker_col, name_col, shares_col, cost_col, cost_is_total) -> list[dict]:
    """Build holdings rows using the EXACT columns the user picked — no guessing."""
    import pandas as pd
    rows = []
    for _, r in df.iterrows():
        raw_ticker = str(r[ticker_col]).strip() if ticker_col != NONE_OPTION else ""
        if not raw_ticker or raw_ticker.lower() == "nan":
            continue
        row = {c: "" for c in COLUMNS}
        row["ticker"] = raw_ticker.upper()
        if name_col != NONE_OPTION:
            val = r[name_col]
            row["name"] = "" if pd.isna(val) else str(val).strip()
        shares = _clean_number(r[shares_col]) if shares_col != NONE_OPTION else 0
        row["shares_owned"] = shares
        if cost_col != NONE_OPTION:
            raw_cost = _clean_number(r[cost_col])
            row["avg_cost"] = round(raw_cost / shares, 4) if (cost_is_total and shares) else raw_cost
        else:
            row["avg_cost"] = 0
        row["type"] = "equity"
        rows.append(row)
    return rows


upload_tab1, upload_tab2 = st.tabs(["📄 Upload CSV", "📸 Upload screenshot"])

with upload_tab1:
    st.caption(
        "For each file, confirm which column is which below — pre-filled with a best guess, "
        "but nothing is used until you can see and (if needed) correct it."
    )
    uploaded_csvs = st.file_uploader(
        "Upload one or more holdings CSVs", type=["csv"], accept_multiple_files=True, key="csv_uploader",
    )
    if uploaded_csvs:
        combined_rows = []
        sig_parts = []
        for f in uploaded_csvs:
            df, had_ragged_rows = _safe_read_csv(f)
            if had_ragged_rows:
                st.warning(
                    f"**{f.name}**: at least one row has more fields than the header — usually "
                    "an unquoted comma inside a value (a name, or a number like '11,845.02'). "
                    "That specific row may have lost a value; check it against the raw preview "
                    "below. Every other row's columns are correctly aligned."
                )

            st.markdown(f"**{f.name}** — {len(df)} rows read")
            with st.expander("Preview raw data", expanded=False):
                st.dataframe(df.head(5), use_container_width=True)

            guess = _guess_column_mapping(df)
            options = [NONE_OPTION] + [str(c) for c in df.columns]

            def _default_index(canon, fallback=None):
                target = guess.get(canon, fallback)
                return options.index(target) if target in options else 0

            wc1, wc2 = st.columns(2)
            with wc1:
                ticker_col = st.selectbox(
                    "Ticker / Symbol column (or Name, if no ticker exists)", options,
                    index=_default_index("ticker", guess.get("name")), key=f"map_ticker_{f.name}_{f.size}",
                )
                name_col = st.selectbox(
                    "Name column", options, index=_default_index("name"), key=f"map_name_{f.name}_{f.size}",
                )
            with wc2:
                shares_col = st.selectbox(
                    "Shares / Quantity owned column", options,
                    index=_default_index("shares_owned"), key=f"map_shares_{f.name}_{f.size}",
                )
                cost_col = st.selectbox(
                    "Cost column (avg cost per share, or total cost)", options,
                    index=_default_index("avg_cost", guess.get("cost_total")),
                    key=f"map_cost_{f.name}_{f.size}",
                )
            cost_is_total = st.checkbox(
                "That cost column is a TOTAL, not per-share — divide by quantity to get avg cost",
                value=("avg_cost" not in guess and "cost_total" in guess),
                key=f"map_costtotal_{f.name}_{f.size}",
            )

            file_rows = _build_rows_from_mapping(df, ticker_col, name_col, shares_col, cost_col, cost_is_total)
            combined_rows.extend(file_rows)
            if ticker_col == NONE_OPTION:
                st.error(f"**{f.name}**: pick a Ticker (or Name) column — nothing was loaded from this file yet.")
            else:
                st.caption(f"→ {len(file_rows)} holding(s) will be loaded from this file with the mapping above.")
            sig_parts.append((f.name, f.size, ticker_col, name_col, shares_col, cost_col, cost_is_total))
            st.divider()

        csv_sig = tuple(sig_parts)
        if st.session_state.get("_last_csv_sig") != csv_sig:
            st.session_state["holdings_rows"] = combined_rows
            st.session_state["_last_csv_sig"] = csv_sig
            if combined_rows:
                st.success(f"Loaded {len(combined_rows)} holding(s) from {len(uploaded_csvs)} file(s) below.")

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
        "ticker": st.column_config.TextColumn("📄 Ticker"),
        "name": st.column_config.TextColumn("📄 Name"),
        "currency": st.column_config.TextColumn("📄 Currency"),
        "exchange": st.column_config.TextColumn("📄 Exchange"),
        "sector": st.column_config.TextColumn("📄 Sector"),
        "region": st.column_config.TextColumn("📄 Region"),
        "notes": st.column_config.TextColumn("📄 Notes"),
        "type": st.column_config.SelectboxColumn("📄 Type", options=["equity", "etf"]),
        "shares_owned": st.column_config.NumberColumn("📄 Shares Owned", min_value=0.0, format="%.4f"),
        "avg_cost": st.column_config.NumberColumn("📄 Avg Cost", min_value=0.0, format="%.4f"),
        "price": st.column_config.NumberColumn("🌐 Price", disabled=True, format="%.4f"),
        "chg_today_pct": st.column_config.NumberColumn("🌐 Today", disabled=True, format="%+.2f%%"),
        "chg_week_pct": st.column_config.NumberColumn("🌐 This Week", disabled=True, format="%+.2f%%"),
        "market_value": st.column_config.NumberColumn("🌐 Value", disabled=True, format="%.2f"),
        "gain_value": st.column_config.NumberColumn("🌐 Gain (£/$/etc)", disabled=True, format="%+.2f"),
        "gain_pct": st.column_config.NumberColumn("🌐 Gain %", disabled=True, format="%+.2f%%"),
    },
    key="holdings_editor",
)
st.caption(
    "📄 = your data (typed in or uploaded) — Ticker, Name, Shares Owned, Avg Cost, etc. are "
    "saved with your holdings. 🌐 = fetched live from Yahoo Finance every time you open the "
    "app (Price, Today/This Week % move, Value, Gain) — never saved, always current. Value/"
    "Gain combine both: your 📄 Shares Owned × Avg Cost against the 🌐 live price, shown in "
    "each stock's own currency, not converted to GBP."
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
