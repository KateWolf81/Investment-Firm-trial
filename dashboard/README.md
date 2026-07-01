# Weekly Briefing Dashboard

A one-page app: edit this week's holdings, click a button, get the full weekly
briefing. No terminal, no `.env` file, no `pip install` — once deployed, it's
just a URL you bookmark.

## Deploy for free (Streamlit Community Cloud) — one-time setup, ~5 minutes

1. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with your GitHub account.
2. Click **New app**, then pick this repository and branch.
3. Set **Main file path** to `dashboard/app.py`.
4. Before deploying, open **Advanced settings → Secrets** and add:
   ```
   ANTHROPIC_API_KEY = "sk-ant-your-real-key-here"
   ```
   This is the one place your key needs to live — it's stored encrypted by
   Streamlit, never committed to the repo.
5. Click **Deploy**. You'll get a permanent URL like
   `https://your-app-name.streamlit.app`.

From then on: open that URL, edit or upload your holdings, click
**Generate this week's briefing**. That's it.

## Running it locally instead

If you'd rather not host it anywhere:

```bash
pip install -r requirements.txt
# .env in the repo root must contain ANTHROPIC_API_KEY=sk-ant-...
streamlit run dashboard/app.py
```

This opens the same dashboard in your browser at `http://localhost:8501`,
using your local `.env` file for the API key instead of Streamlit secrets.

## Notes

- Market data comes from Yahoo Finance via `yfinance`. This requires normal
  outbound internet access — it will **not** work inside a network-restricted
  sandbox (like a locked-down Claude Code container), but works fine on
  Streamlit Community Cloud or your own machine.
- Uploading new holdings only requires filling in `ticker`, `sector`,
  `exchange`, and `region` reasonably — analysts route coverage automatically
  from those fields (see `config/holdings.py`). There's no per-ticker code to
  update.
