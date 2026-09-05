# NIFTY 50 Volatility Screener

Pulls live NIFTY 50 constituent quotes from the NSE India public JSON endpoint
and ranks the index by dispersion of intraday returns, reporting standard
deviation, skewness and excess kurtosis for the five most volatile names. The
interesting engineering content here is less the statistics than the **scraping
layer**: NSE actively blocks non-browser clients, so the script implements the
cookie handshake, header spoofing and retry logic needed to get a JSON response
at all.

## How it works

**Step 1 — session establishment (`establish_session`).** NSE's API endpoints
reject requests that arrive without the cookies its front-end sets. The script
therefore first issues a plain `GET` to `nseindia.com` through a
`requests.Session()`, which captures those cookies, then sleeps 2 seconds before
touching the API. Skipping this handshake returns an HTML block page rather than
JSON.

**Step 2 — data fetch (`fetch_data`).** Requests
`/api/equity-stockIndices?index=NIFTY%2050` with a full browser header set
(`User-Agent`, `Accept`, `Accept-Language`, `Referer`) and up to 3 retries with
a 5-second backoff. Failure handling is separated by cause, which is what makes
the script debuggable in practice:

| Exception | Cause it diagnoses |
|---|---|
| `JSONDecodeError` | Blocked — an HTML page was served instead of JSON (first 500 chars printed) |
| `HTTPError` | 4xx/5xx from NSE, status code reported |
| `RequestException` | Network/timeout failure |

**Step 3 — analysis (`analyze_volatility`).** Coerces `lastPrice` and
`previousClose` to numeric (invalid rows dropped), computes the day's return per
stock,

```
Return (%) = (lastPrice − previousClose) / previousClose × 100
```

then applies rolling 5-observation `std`, `scipy.stats.skew` and
`scipy.stats.kurtosis` (both with `bias=False` for the sample-corrected
estimator, and `kurtosis` returning *excess* kurtosis, i.e. normal = 0). The top
5 rows by the resulting volatility column are printed with symbol, return,
volatility, skewness and kurtosis.

## Reading the statistics

- **Standard deviation** — dispersion of returns; the conventional volatility proxy.
- **Skewness** — asymmetry. Negative skew means the left tail is longer: large
  losses are more extreme than large gains, which is the typical equity pattern.
- **Excess kurtosis** — tail weight relative to a normal distribution. Positive
  values mean fat tails, and are the reason a Gaussian VaR understates real
  downside risk.

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests pandas numpy scipy

python3 top_volatile_stocks.py
```

Must be run during or after NSE market hours for `lastPrice` to be meaningful.
The endpoint is unauthenticated but rate-limited and geo-restricted — from
outside India, or from a datacentre IP, expect the block page that the
`JSONDecodeError` branch reports.

## Repo structure

```
top_volatile_stocks.py    NSE session handshake -> NIFTY 50 quote fetch -> volatility/skew/kurtosis ranking
```

## Limitations

Worth stating explicitly, because they bound what the output means:

- **The rolling window is cross-sectional, not temporal.** The NSE endpoint
  returns a *single snapshot* — one row per stock, not a time series. So
  `.rolling(window=5)` slides down the list of *stocks* in whatever order NSE
  returned them, and each "volatility" figure is the standard deviation of five
  neighbouring companies' daily returns. It is a measure of dispersion *across
  the index*, not of any individual stock's volatility over time, and the
  ranking is sensitive to row order. Computing true per-stock volatility
  requires accumulating this snapshot daily, or sourcing a historical bar series
  (e.g. `yfinance` with `.NS` suffixes) and taking the rolling std of each
  stock's own return history.
- **Five observations.** Skewness and kurtosis estimated from a 5-point window
  have very large standard errors; 3rd and 4th moments need substantially more
  data before they are informative.
- **One return per name.** A single close-to-last-price move is a point
  observation, not a distribution, so it cannot support a volatility estimate on
  its own.
- **Unofficial endpoint.** `equity-stockIndices` is undocumented and can change
  shape or be withdrawn without notice; the column-existence guard on
  `lastPrice` / `previousClose` is there for exactly that reason.
