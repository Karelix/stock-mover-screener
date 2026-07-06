# Stock Mover Screener

Pre-market short-candidate research screener for stocks with large upside moves.

This repository is being built in phases. Phase 1 defines the tradable universe:

- US common stocks
- No ETFs, warrants, preferreds, units, rights, or closed-end funds
- Minimum price, market cap, and average dollar volume thresholds
- Biotech is intentionally included

Phase 2 scans that universe for abnormal pre-market upside movers:

- Premarket percentage move
- Gap from previous close
- Premarket volume and dollar volume
- Relative volume
- ATR-adjusted move

Use `scan_universe_premarket_movers` to apply Phase 1 first, then rank the
remaining records by pre-market mover strength.

Phase 3 filters and annotates liquidity:

- Minimum premarket share volume
- Minimum premarket dollar volume
- Minimum average dollar volume
- Maximum bid/ask spread when spread data is available
- Low-float and very-low-float risk flags

Use `scan_tradeable_premarket_candidates` to apply Phases 1-3 in order.

Phase 4 scores fundamental weakness without filtering records out:

- Negative net income
- Negative operating cash flow
- Negative free cash flow
- Declining revenue
- Weak current ratio
- High debt/equity
- Low cash runway
- No meaningful revenue
- High price/sales after the move
- Missing fundamental data warnings

Use `scan_fundamental_premarket_candidates` to apply Phases 1, 2, optional
Phase 3 liquidity, and Phase 4 scoring.

Phase 5 scores dilution and capital-raise risk without filtering records out:

- Active shelf registration
- Recent offering
- S-1 / S-3 registration filings
- 424B / prospectus supplement filings
- ATM offering
- Registered direct offering
- Private placement
- Warrants
- Convertible debt or notes
- Equity line facilities
- Shares outstanding growth
- Repeated offering history

Use `scan_dilution_premarket_candidates` to apply Phases 1, 2, optional
Phase 3 liquidity, Phase 4 fundamentals, and Phase 5 dilution-risk scoring.

Phase 6 classifies catalyst quality:

- Strong catalysts such as earnings/guidance, acquisition, FDA approval, material
  contracts, refinancing, or profitability inflection
- Medium catalysts such as analyst upgrades, product launches, partnerships, or
  sector sympathy
- Weak catalysts such as vague AI/crypto claims, non-binding LOIs, unnamed
  partners, no financial terms, strategic alternatives, social media/meme moves,
  old news, or short-squeeze headlines
- None or unknown when there is no obvious catalyst or missing catalyst data

Use `scan_catalyst_premarket_candidates` to apply Phases 1, 2, optional Phase 3
liquidity, Phase 4 fundamentals, Phase 5 dilution risk, and Phase 6 catalyst
classification.

Phase 7 scores hype and crowd-attention signals:

- Meme keywords and retail-trader phrasing
- Reddit, Stocktwits, social-media, influencer, or viral language
- Short-squeeze language
- AI, crypto, blockchain, quantum, and similar buzzword themes
- Social mention spikes
- Headline velocity and multiple same-day headlines
- Low-float hype amplification
- Large premarket move paired with attention signals

Use `scan_hype_premarket_candidates` to apply Phases 1, 2, optional Phase 3
liquidity, Phase 4 fundamentals, Phase 5 dilution risk, Phase 6 catalyst
classification, and Phase 7 hype scoring.

Phase 8 scores squeeze and shortability danger:

- Low and very-low float
- High short interest and days to cover
- High borrow fee
- Hard-to-borrow status
- Low or unavailable borrow inventory
- Extreme premarket move
- High hype score
- Repeated halts
- Call-volume explosion

Use `scan_squeeze_premarket_candidates` to apply Phases 1, 2, optional Phase 3
liquidity, Phase 4 fundamentals, Phase 5 dilution risk, Phase 6 catalyst
classification, Phase 7 hype scoring, and Phase 8 squeeze/shortability risk.

Phase 9 creates final pre-market labels:

- Prime Watch
- Watch Only
- Too Dangerous
- Likely Real Catalyst
- Needs More Data
- Ignore

Use `scan_labeled_premarket_candidates` to apply Phases 1-9. The final label is
added on top of the candidate object; all previous metrics, scores, reasons, and
warnings remain available. Use `candidate_to_summary_row` for a flat table row
and `candidate_to_full_dict` when you want every nested detail for a ticker.

## CLI runner

Run the full scanner against provider-normalized CSV records:

```powershell
$env:PYTHONPATH = "src"
python -m stock_mover_screener.cli scan examples/sample_premarket.csv --output results.csv
```

If `--output` is omitted, summary CSV is printed to stdout. The CLI loads the
JSON rule files from `config/` by default and writes one summary row per passing
candidate. If the package is installed, the `stock-mover-screener scan ...`
console command is also available.

## Streamlit dashboard

Install the project with the dashboard extra:

```powershell
$env:SETUPTOOLS_USE_DISTUTILS = "stdlib"
python -m pip install -e ".[dashboard]"
```

Then run the app:

```powershell
python -m streamlit run src/stock_mover_screener/dashboard.py
```

The dashboard reads the sample CSV by default, accepts a CSV upload, applies the
same scanner rules as the CLI, filters the summary table, exports filtered rows,
and shows full nested detail for a selected ticker.

## Provider credentials

Real-data adapters should read credentials from a local `.env` file. Start from
the template:

```powershell
Copy-Item .env.example .env
```

Fill in the provider keys you want to use. Alpaca needs `ALPACA_API_KEY_ID` and
`ALPACA_API_SECRET_KEY`; SEC EDGAR does not need a key, but requests should send
a descriptive `SEC_USER_AGENT`.

## Alpaca market data

`AlpacaMarketDataProvider` reads Alpaca credentials from `.env` and normalizes
market-data fields used by the screener:

```python
from stock_mover_screener.providers import AlpacaMarketDataProvider

provider = AlpacaMarketDataProvider.from_env()
records = provider.build_premarket_records(["AAPL", "TSLA"])
```

This first adapter covers prices, pre-market volume, prior close, average dollar
volume, ATR percentage, bid/ask, and Alpaca news headlines. It does not provide
fundamentals, market cap, float, SEC dilution signals, or borrow data; those
records should be merged with SEC/FMP/FINRA adapters as we add them.

## SEC EDGAR data

`SecEdgarProvider` reads `SEC_USER_AGENT` from `.env`, maps tickers to CIKs,
fetches company submissions and XBRL company facts, and normalizes fundamental
and dilution-friendly filing fields:

```python
from stock_mover_screener.providers import SecEdgarProvider

provider = SecEdgarProvider.from_env()
records = provider.build_company_records(["AAPL", "TSLA"])
```

This adapter covers recent filings, registration/offering flags, offering count,
revenue, prior-year revenue, net income, operating cash flow, capex, cash,
current ratio inputs, debt/equity inputs, shares outstanding, and share-count
growth. It does not fetch full filing text yet; it uses SEC submissions metadata
and companyfacts JSON.

## FMP reference data

`FmpReferenceProvider` reads `FMP_API_KEY` from `.env` and normalizes Financial
Modeling Prep profile, share-float, market-cap, and financial statement data:

```python
from stock_mover_screener.providers import FmpReferenceProvider

provider = FmpReferenceProvider.from_env()
records = provider.build_reference_records(["AAPL", "TSLA"])
```

This adapter covers company profile, security type, market cap, average volume,
average dollar volume, float shares, shares outstanding, revenue, prior-year
revenue, net income, operating cash flow, capex, free cash flow, cash, current
assets/liabilities, current ratio, debt, equity, and debt/equity. Use it as a
convenience fallback next to SEC, not as a replacement for SEC filing analysis.

## FINRA short interest

`FinraShortInterestProvider` downloads and parses FINRA short-interest files.
No API key is required:

```python
from stock_mover_screener.providers import FinraShortInterestProvider

provider = FinraShortInterestProvider()
records = provider.build_short_interest_records(
    ["AAPL", "TSLA"],
    float_shares_by_symbol={"AAPL": 15_000_000_000, "TSLA": 3_000_000_000},
)
```

This adapter covers short-interest shares, settlement date, days to cover,
average daily volume, and short interest as a percentage of float when float
shares are supplied. It does not provide borrow fees, hard-to-borrow status, or
live borrow availability.

The screener should produce a watchlist for review, not automatic trade signals.
