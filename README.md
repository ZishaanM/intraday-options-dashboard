# Intraday Options Dashboard

A Streamlit app that finds past trading days whose intraday path matches today's, forecasts the move to the close from those days, and scores same-day option strikes with Black-Scholes against that forecast.

**For reviewers:** Python · Streamlit · Plotly · pandas / NumPy / SciPy · solo · [screenshots](Dash-pics/)

![Dashboard home tab: SPY intraday path with predicted close and confidence bands](Dash-pics/Screenshot%202025-12-30%20192651.png)

## Problem

A theoretical option price doesn't tell you whether a strike's break-even is reachable today. The project tests a mentor's hypothesis: can the shape of a day so far (its moves from the open, the prior close, and the intraday high and low) say something useful about where it will close? It then turns that forecast into a per-strike buy/no-buy signal.

## Approach

- **Similarity search, not a fitted model.** `find_sim_history` in `main.py` takes the reference bar's four features (`ret_from_open`, `ret_from_p_close`, `ret_from_high`, `ret_from_low`). It keeps historical bars at the same clock time where every feature is within a threshold, ranks them by the sum of absolute differences, and keeps the top 100. The threshold starts at 0.001 and widens by 0.001 until at least 30 matches are found. Fixing the time of day keeps the comparison like-for-like (a +1% move at 10:00 is not a +1% move at 15:30).
- **Forecast with uncertainty.** `pred_ret` takes the mean and standard deviation of the matches' `ret_to_close` and builds a normal 95% confidence interval. The UI converts these into a predicted close price, a 95% band, and a 1σ band.
- **Same-day option scoring.** `black_scholes_price` is a hand-written European pricer that measures time to expiry in trading hours (year = 252 × 6.5 h), so a noon-to-close expiry is priced correctly. For a ladder of 15 strikes ($2.50 apart, starting about $10 below spot), the tables compare each option's break-even to the forecast bands and label it **STRONG YES / Yes / No / STRONG NO**. The advanced table adds Delta, Gamma, and probability ITM.
- **Replay, not live.** `config.py` pins a reference date and time (default 2010-06-08 at 12:00), and the app replays that moment from local data. Data started in a PostgreSQL warehouse and was later exported to Parquet so the dashboard runs offline.

**Simplifications to know about:** volatility is a constant (`implied_vol()` returns 0.32161) and the risk-free rate is a constant 3.961%. The advanced table's **Bid / Ask / Volume columns are placeholders** (literally `"Fake"`), not market quotes. No option-chain data is used anywhere.

## How to run

### Prerequisites

- Python 3 (tested on 3.12)
- `returns.parquet` in the repo root. It is gitignored and not published, so you have to bring your own (see [Getting `returns.parquet`](#getting-returnsparquet)).

### Install

```bash
git clone https://github.com/ZishaanM/intraday-options-dashboard.git
cd intraday-options-dashboard
python -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

Set the moment to replay in `config.py`:

```python
reference_date = '20100608'  # YYYYMMDD
reference_time = 1200        # HHMM, 24-hour (1200 = 12:00 PM)
```

The dashboard needs no environment variables. Database credentials are only used by the export/ETL scripts (see below).

### Run

```bash
streamlit run UI.py     # dashboard at http://localhost:8501
python main.py          # CLI: matches, forecast, and actual vs predicted for the reference bar
```

### Verify

- **CLI:** prints the number of similar patterns found, the predicted return to close with its 95% CI, the threshold used, the actual return to close, the prediction error and z-score, whether the actual falls inside the CI, and the five closest historical days.
- **Dashboard:** a green "Found N similar historical patterns" banner. **Home** shows the reference day's price path up to the reference time, the predicted-close and CI markers at 16:00, and a color-coded strike table (use the Call/Put selector to switch). **Data** shows the forecast numbers next to the actual return to close. **Adv. Table** adds the Greeks.
- Logs go to `log/<module>.log` (created on first run) and errors also go to `cron.log`.

### Getting `returns.parquet`

The app reads one table, `returns`, with one row per (date, minute) bar:

| Column | Type | Meaning |
|--------|------|---------|
| `date` | int | Trading date, `YYYYMMDD` (e.g. `20100608`) |
| `time` | int | Bar time, `HHMM` (e.g. `930`, `1200`) |
| `close` | float | Price at that bar |
| `ret_from_open` | float | Return from the day's open |
| `ret_from_p_close` | float | Return from the previous day's close |
| `ret_from_high` | float | Return from the day's high so far |
| `ret_from_low` | float | Return from the day's low so far |
| `ret_to_close` | float | Return from this bar to the day's close (the forecast target) |

You can get it two ways:

1. **Export it from the original PostgreSQL warehouse** (only if you have access). Copy `.env.example` to `.env`, fill in the `gcp_*` values, and load them into your shell. In `archive/parquet_conversion_fast.py`, set `START_FROM_TABLE = "returns"` so it skips the large raw minute tables. Run it from the repo root so that `z_util` is importable and the file lands next to `UI.py`:

   ```bash
   set -a; source .env; set +a
   PYTHONPATH=. python archive/parquet_conversion_fast.py
   ```

   The `returns` table was computed inside that warehouse from minute-bar tables copied in from an Azure MySQL source (`archive/python_ETL_ts.py`). The SQL that derives the return columns is not in this repo.

2. **Build your own** from any minute-bar data using the schema above. Write it with `df.to_parquet("returns.parquet")`.

### Gotchas

- **Missing data:** without `returns.parquet`, both entry points fail with "Parquet file not found" / "Make sure the parquet files exist in the script directory".
- **Types matter:** `date` and `time` must be integers. String dates won't match the reference date and the dashboard stops silently.
- **The reference bar must exist:** there must be a row exactly at `reference_date` / `reference_time`.
- **The ticker box is a label only.** The `returns` data has no ticker column, so typing AAPL still analyzes whatever single underlying your parquet contains (the UI defaults to SPY).
- **Lookahead:** the search runs over the whole dataset, so it can match later dates and the reference day itself. Treat the output as a demo, not a backtest.
- **Memory:** the full parquet is loaded into memory (cached per process).
- `activate_options_dash.ps1` activates a venv outside this repo (`..\options_pricer_venv`). Use your own venv instead.
- `archive/` holds one-off ETL, cleaning, and exploration scripts from the database era. They read credentials from the environment variables in `.env.example` and need extra packages (`archive/requirements.txt`, plus `pymysql` for the Azure scripts).

## What's interesting in the code

- **`main.py` → `find_sim_history` and `pred_ret`:** the whole forecasting idea in about 80 lines. Look at the adaptive threshold loop (widen until at least 30 neighbors, cap at 100) and how a same-clock-time filter plus an L1 ranking stands in for a trained model.
- **`main.py` → `black_scholes_price` and `calc_advanced_table_data`:** intraday time-to-expiry scaling, Greeks computed from `d1` / `d2`, and the break-even vs. forecast-band rules that turn prices into a recommendation.

## Stack

Python · Streamlit · Plotly · pandas · NumPy · SciPy · PyArrow / Parquet · SQLAlchemy + PostgreSQL (legacy data pipeline)
