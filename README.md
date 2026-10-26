# India Market Daily Agent — High Momentum + Fundamental Quality

Runs at 8:00 AM IST on trading days: reconciles earlier picks, builds market context (Gift Nifty, global cues, VIX),
scans **Nifty 500** for **high-momentum, fundamentally stronger** names, and writes **2 option scalps, 2 intraday and 2 short-term** picks to Google Sheets (and Telegram).

Design rule: **all prices and levels are computed in code**. Claude only writes the wording and (optionally) looks up
Gift Nifty. Every pick must pass `agent/validate.py` (stop on the right side, R:R >= MIN_RR) or it is dropped.

## What changed for high-momentum + quality short-term trades

- **Momentum score** (0–~10): 5/10/20-day ROC, relative strength vs Nifty, 20-day breakout + volume, near 52w high, EMA stack, RSI momentum zone, volume surge.
- **Fundamental score** (0–6, best-effort via yfinance): ROE, profit margin, debt/equity, revenue/earnings growth, reasonable PE. Missing data = 0 (does not kill the candidate).
- **Composite** = momentum + 0.75 × fund. Short-term picks require `momentum_score >= MIN_MOMENTUM_SCORE` (default 3) and `composite >= MIN_COMPOSITE` (default 3.5), with light sector diversification.
- Report surfaces the top momentum+quality names even when they are not selected as formal picks.

## Quick start
    pip install -r requirements.txt
    python -m pytest -q                         # core tests
    python main.py run --demo --force           # offline synthetic data, writes out/store.json + out/report_*.txt
    python main.py run --local                  # LIVE data, local JSON store
    python main.py run --notify                 # LIVE data, Google Sheet (needs SHEET_ID + service account)

## Connect the Google Sheet
1. Upload `trade_reco_tracker.xlsx` to Drive, open with Google Sheets, delete the yellow example rows.
2. Google Cloud: create a service account, enable the Sheets API, download its JSON key.
3. Share the sheet with the service account's email (Editor).
4. Set `SHEET_ID` and `GOOGLE_SA_JSON` (see `.env.example`). The agent writes only input cells, never formula columns.

## Deploy
Push to GitHub, add the secrets used in `.github/workflows/daily.yml`. Cron is 02:30 UTC = 08:00 IST.

## How picks are built
- **Option scalp** (NIFTY, BANKNIFTY): direction from Gift Nifty gap (fallback: global bias + EMA20). Levels are on the
  UNDERLYING index; Direction is the index direction, Instrument says CE/PE (for a PE scalp you BUY the PE). Entry is a
  trigger to confirm after 9:30. Skipped when India VIX >= VIX_SKIP_SCALP.
- **Intraday**: breakout/breakdown of prior day high/low, risk = 0.6 ATR, T1 = 1.6R, T2 = 2.4R. Long or short.
- **Short-term** (primary focus): long only (cash segment), ranked by composite (high momentum + fundamental quality).
  Entry near prior close, stop = tighter of 10-day low / 2 ATR (min 1 ATR), T1 = 2R, T2 = 3R. Valid 3 sessions, hold up to 10.
- **Reconcile**: daily candles; if SL and target are both touched in one candle, SL is assumed first. Intraday/scalps
  are squared off at the close if unresolved.

## Environment knobs (optional)
| Variable | Default | Meaning |
|----------|---------|---------|
| `MIN_TURNOVER_CR` | 20 | Minimum 20-day average turnover (₹ Cr) |
| `MIN_MOMENTUM_SCORE` | 3 | Floor for short-term momentum score |
| `MIN_COMPOSITE` | 3.5 | Floor for momentum + fund composite |
| `MIN_RR` | 1.5 | Minimum reward:risk on every pick |
| `VIX_SKIP_SCALP` | 22 | Skip option scalps above this India VIX |

## Known limits (read these)
- Gift Nifty has no clean free API. Order: `GIFT_NIFTY_OVERRIDE` -> your JSON URL -> Claude web search (sanity-checked
  within 3% of Nifty close) -> unavailable (bias then uses global cues only and the report says so).
- Option premiums/strikes are not fetched. Strike is ATM of the trigger level; confirm expiry and premium live.
- Yahoo data for NSE can be delayed/incomplete; fundamentals via yfinance are sparse for many Indian names — treat fund_score as a soft quality boost, not a hard filter.
- Swap `LiveData` for Kite Connect (or another broker API) for better price data and richer fundamentals if needed.
- NSE holidays use the BSE calendar as a proxy plus `data/holidays.txt`. Verify each year.
- Backtest before trusting any rule: the Performance tab will show win rate / avg R per type as data accumulates.
- Not investment advice. Do not auto-execute; if you ever do, SEBI's retail algo rules (broker API, strategy ID, static IP) apply.
