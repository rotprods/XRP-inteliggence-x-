# H7 Provider Contract Reconciliation — 2026-09-22

Status: **SAFE READ-ONLY GOVERNANCE WAVE COMPLETE · REAL CORPUS STILL BLOCKED**

## Exact repository truth at wave start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical base: `main@a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Base tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed immediately before the wave: **none**
- Latest merged PR: `#30`
- Latest exact verified feature head: `cf8b736a31647f5695211edf8d36b199bbe989ee`
- Verification OS evidence for that head: run `35660067501`, FAST job `106532947585` — **PASS**
- Workflow runs found for current `main@a9ad231...`: **0**, therefore exact-current-main CI = **NOT_RUN**
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**
- Production: **BLOCKED**
- `probability_calibrated=false`
- `decision_authority=false`
- `execution_weight=0.0`

## Why this wave was selected

Canonical H6/H7 mechanics are already merged and verified. The immediate scientific frontier is a
real immutable point-in-time XRP DatasetVersion, but `STATE.md` and `HANDOFF.md` correctly block a
large historical corpus until provider terms/regional restrictions and the retention policy are
reconciled.

No provider-specific `HistoricalAdapterV2` was found on canonical main. Creating a second historical
architecture would be a regression. The highest-value collision-safe action was therefore to close
the provider-contract information gap while preserving the existing adapter seam.

## Official-source findings reviewed on 2026-09-22

### Binance

Reviewed official sources:

- `https://data.binance.vision/`
- `https://academy.binance.com/en/articles/how-to-retrieve-binance-spot-market-data-efficiently`
- `https://developers.binance.com/en/docs/products/spot/PROD-TERMS-OF-USE`
- Binance Developer Docs for `data-api.binance.vision` public `NONE`-security endpoints.

Finding: Binance officially documents downloadable historical Spot market data and public read-only
market-data endpoints. This engineering review did **not** establish a provider/region-specific
licence granting the project unrestricted long-term retention or redistribution. Regional
availability is not assumed.

Decision: public bounded smoke is eligible; a large retained corpus remains **BLOCKED**.

### Kraken

Reviewed official sources:

- `https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data`
- `https://www.kraken.com/legal/eea-terms`

Finding: Kraken's support material, updated 2026-09-16, documents downloadable OHLCVT CSV data for
each currency pair from market inception and explicitly states the files may be used in code,
converted to other formats or imported into applications. Kraken EEA Terms effective 2026-06-29
apply to EEA clients, including Spain.

Decision: Kraken is a strong candidate for the first independent USD historical adapter, but the
project still lacks explicit owner acceptance of long-term retention/derived-feature policy and no
redistribution right is inferred. Promoted large retention remains **BLOCKED**.

### Coinbase

Reviewed official sources:

- current Coinbase developer market-data documentation;
- `https://www.coinbase.com/legal/developer-platform/terms-of-service` (last modified 2026-06-23).

Finding: current developer documentation confirms market-data interfaces. This wave did not find an
explicit retained-history/redistribution grant suitable for the intended corpus.

Decision: keep Coinbase as an independent USD research source candidate; retained historical
promotion remains **BLOCKED** pending terms mapping.

## Temporal / provenance consequence

A provider-specific historical adapter may now be engineered safely, but retrospective data fetched
today for a historical prediction time must **not** become `STRICT_REPLAY`. Under the canonical
`HistoricalObservation` contract it must be:

- `RECONSTRUCTED_PIT` with a valid `reconstruction_basis_id`, when reconstruction is defensible; or
- `INELIGIBLE` otherwise.

This preserves `available_at` semantics and prevents future-fetched history from being laundered into
an ex-ante dataset.

## Code / security / QA review

- CODE REVIEW: **PASS** — this wave changes governance/checkpoint material only; no runtime or model
  code is added and no parallel adapter/backfill architecture is introduced.
- SECURITY REVIEW: **PASS** — no credentials, API keys, account endpoints, order routes, wallet
  actions, private keys, custody or leverage surfaces are introduced.
- TEMPORAL / PROVENANCE REVIEW: **PASS** — `STRICT_REPLAY` remains fail-closed and future-fetched
  data is explicitly constrained to `RECONSTRUCTED_PIT`/`INELIGIBLE`.
- SOURCE-INDEPENDENCE REVIEW: **PASS** — Binance USDT and Kraken/Coinbase USD remain semantically
  distinct; one exchange is not promoted as independent consensus.
- QA: **PASS for document consistency and deterministic source-manifest hashing**.
- Exact branch CI: **NOT_RUN** by design; the workflow is PR-triggered and no PR is opened merely to
  create CI activity.
- DEEP: **NOT_RUN**
- RELEASE: **NOT_RUN**

## Blocker and resume condition

`LARGE_RETAINED_BACKFILL = BLOCKED`.

Resume real-corpus promotion only when:

1. the selected provider's applicable terms are mapped to the intended retained observations and
   derived features;
2. the project owner explicitly accepts the retention policy;
3. regional/access constraints are recorded;
4. redistribution/attribution assumptions are explicit;
5. the first provider-specific adapter passes deterministic fixture, provenance, temporal and
   security tests.

## Next highest-value bounded WorkUnit

Implement **one** provider-specific `HistoricalAdapterV2` on the existing
`HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2` seam.

Recommended sequencing:

1. Kraken USD historical OHLCVT adapter as the first independent-source candidate because official
   downloadable history is explicitly documented as usable in code.
2. Deterministic synthetic/minimal fixtures first; no large retained provider payload.
3. Force retrospective imports to `RECONSTRUCTED_PIT` unless the evidence was genuinely fetched
   before the prediction time.
4. Add a second independent provider only after the first adapter contract is green; do not fuse USD
   and USDT.
5. Materialize only a tiny bounded sample after retention approval, then build a content-addressed
   DatasetVersion and run H6 B0-B4 versus H7 on exactly matched OOS folds.
6. Preserve `NO_DEMONSTRATED_REGIME_SKILL` and `INSUFFICIENT_EVIDENCE` as valid outcomes.

Do not open or revive PR #13/#15. Their SemanticBrain/COS20D/Graphify and microstructure work is
already in canonical main.
