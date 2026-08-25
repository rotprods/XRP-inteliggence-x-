# FRED/ALFRED Point-in-Time Adapter v0.5

## Contract

The adapter uses the official FRED API endpoints for:

- series vintage dates: `https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html`;
- series observations: `https://fred.stlouisfed.org/docs/api/fred/series_observations.html`.

The API key is read from `FRED_API_KEY`, used only for the HTTPS request and redacted from provenance URLs before persistence. It is never committed, written to Drive, emitted in reports or included in adapter representations.

## Two-phase ingestion

```text
phase 1: discover vintage publication dates
  ↓
phase 2: query each vintage and record the values available on that date
```

Every record uses:

- `observed_at`: the series observation date;
- `available_at`: the FRED vintage publication date;
- `revision`: the ordered vintage index;
- immutable raw response SHA-256;
- a dataset-specific point-in-time catalog entry.

An observation is rejected if its vintage date precedes its observation date. Missing FRED values (`.`) are retained explicitly as `value=null, missing=true` rather than silently dropped or forward-filled.

## Initial macro and cross-asset coverage

The registry contains:

- US 2Y, 10Y and 30Y Treasury yields;
- 10Y real yield;
- broad trade-weighted dollar index;
- Chicago Fed financial conditions;
- M2;
- S&P 500;
- Nasdaq 100;
- VIX;
- WTI and Brent;
- regular gasoline;
- Henry Hub natural gas;
- global cocoa price as an exploratory series with initial weight `0.0`.

Cocoa is stored for falsification and exploratory analysis, not assumed to predict XRP.

## Backfill example

```bash
export FRED_API_KEY='...'
python scripts/backfill_fred_series_v05.py \
  --series-id DGS10 \
  --observation-start 2020-01-01T00:00:00Z \
  --observation-end 2021-01-01T00:00:00Z \
  --vintage-start 2020-01-01 \
  --vintage-end 2021-12-31
```

Windows longer than one year require an explicit override. Large production backfills must be staged, rate-limited, manifested and restored in a drill before model calibration.

## Limitations

- Vintage publication is represented at UTC day granularity because the API exposes dates rather than exact release timestamps for this workflow.
- Market series distributed through FRED may have different licensing or revision characteristics; each series still requires a licence/source register entry.
- This adapter does not implement economically invalid forward-fill.
- A passing adapter test does not establish full backfill completeness.

Production remains blocked until all registered series have completed manifests, missing/revised observations are quantified and walk-forward evaluation consumes only records available at each decision timestamp.
