# NIFTY 50 Volatility Screener

Ranks NIFTY 50 constituents by their own **realised volatility**, computed from a
daily price history per symbol and annualised. Skewness and excess kurtosis are
reported alongside it, estimated over the full sample.

The NSE public JSON endpoint is still used, but only for what it can actually
supply: today's constituent list. NSE actively blocks non-browser clients, so
that fetch implements the cookie handshake, header spoofing and retry logic
needed to get JSON back at all — and falls back to a static list when it fails,
so the screener survives the scraper.

## How it works

**Step 1 — session establishment (`establish_session`).** NSE's API endpoints
reject requests that arrive without the cookies its front-end sets. The script
first issues a plain `GET` to `nseindia.com` through a `requests.Session()`,
which captures those cookies, then sleeps 2 seconds before touching the API.
Skipping this handshake returns an HTML block page rather than JSON.

**Step 2 — constituent list (`fetch_snapshot`, `constituents`).** Requests
`/api/equity-stockIndices?index=NIFTY%2050` with a full browser header set and up
to 3 retries with a 5-second backoff, then takes the `symbol` column (dropping
the index row itself). Failure handling is separated by cause:

| Exception | Cause it diagnoses |
|---|---|
| `JSONDecodeError` | Blocked — an HTML page was served instead of JSON (first 500 chars printed) |
| `HTTPError` | 4xx/5xx from NSE, status code reported |
| `RequestException` | Network/timeout failure |

If every retry fails, `constituents` returns `NIFTY50_FALLBACK`, a static symbol
list. `--no-nse` skips the scrape entirely.

**Step 3 — price history (`fetch_history`).** Downloads `--period` of daily bars
per symbol via `yfinance` (`SYMBOL.NS`), split- and dividend-adjusted
(`auto_adjust=True`), and returns a frame indexed by **date** with **one column
per stock**. `YAHOO_OVERRIDES` maps NSE symbols whose Yahoo ticker has drifted
(e.g. `TATAMOTORS` → `TMPV` after the demerger); without it such a name silently
vanishes from the ranking.

**Step 4 — analysis (`analyze_volatility`).** Log returns are taken down each
column, so every window walks one stock's own history:

```
r_t = ln(P_t / P_{t-1})
sigma_ann = std(r, ddof=1) x sqrt(252) x 100      # annualised, in %
```

Two volatility columns are reported — `Vol {window}d`, the trailing window
(default 21 trading days ≈ 1 month), and `Vol full`, the whole sample — because
a name can be quiet over the year and violent this month. Skewness and
`scipy.stats.kurtosis` (both `bias=False`; kurtosis is *excess*, normal = 0) use
the full sample, since 3rd and 4th moments need hundreds of observations to
carry information. Symbols with fewer than `--min-obs` returns are dropped and
**named** in the output rather than silently disappearing.

## Reading the statistics

- **Annualised volatility** — dispersion of that stock's own daily log returns,
  scaled by `sqrt(252)`, so it is comparable to implied vol quoted on options.
- **Skewness** — asymmetry. Negative skew means the left tail is longer: large
  losses are more extreme than large gains, the typical equity pattern.
- **Excess kurtosis** — tail weight relative to a normal distribution. Positive
  values mean fat tails, and are the reason a Gaussian VaR understates real
  downside risk.

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests pandas numpy scipy yfinance

python3 top_volatile_stocks.py                          # 1y history, 21d window, top 5
python3 top_volatile_stocks.py --period 2y --window 63  # longer sample, quarterly window
python3 top_volatile_stocks.py --no-nse --top 10        # skip the NSE scrape
```

Sample output:

```
5 Most Volatile Stocks (annualised, trailing 21 trading days):
    symbol  Vol 21d (%)  Vol full (%)  Skewness  Kurtosis  Obs  Return 1d (%)
  ADANIENT        40.82         35.42     -0.11      6.08  251          -0.23
ADANIPORTS        32.32         27.98      0.04      4.56  249           0.05
BHARTIARTL        26.62         20.20     -0.08      1.68  251          -1.18
  HINDALCO        26.42         28.17     -0.65      1.30  249           0.10
       TCS        26.28         28.23     -0.52      3.81  251          -0.07
```

Unlike the previous version, this does not need to be run during market hours —
it ranks on closed daily bars. The NSE endpoint is unauthenticated but
rate-limited and geo-restricted; from outside India, or from a datacentre IP,
expect the block page that the `JSONDecodeError` branch reports, after which the
static constituent list takes over.

## Repo structure

```
top_volatile_stocks.py    NSE constituent fetch -> per-symbol daily history -> annualised vol / skew / kurtosis ranking
```

## Limitations

- **Corporate actions beyond splits and dividends.** `auto_adjust=True` handles
  splits and dividends, not demergers or large bonus-like adjustments. A single
  unadjusted gap dominates the 3rd and 4th moments — e.g. over a 2-year sample
  `TRENT` shows skew ≈ −5.6 and excess kurtosis ≈ 70, which is one print, not a
  tail property. Treat extreme moments as a data-quality flag first.
- **Realised, not forward-looking.** Trailing standard deviation is a backward
  estimate and assumes returns are i.i.d. within the window. It says nothing
  about tomorrow, and it is not implied vol; volatility clusters, so a GARCH or
  EWMA estimator would weight recent observations more heavily.
- **Equal-weighted daily closes.** Close-to-close ignores intraday range, so it
  understates vol relative to Parkinson/Garman-Klass estimators that use the
  high and low.
- **Two vendors, two failure modes.** The constituent list depends on an
  undocumented NSE endpoint that can change shape (hence the fallback), and the
  history depends on Yahoo tickers that can be renamed (hence
  `YAHOO_OVERRIDES`). Both are unofficial sources.
