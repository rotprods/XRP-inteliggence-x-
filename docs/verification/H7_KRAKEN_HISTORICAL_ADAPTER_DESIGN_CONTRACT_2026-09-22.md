# H7 Kraken Historical Adapter Design Contract — 2026-09-22

Status: **SAFE READ-ONLY DESIGN WAVE COMPLETE · IMPLEMENTATION DEFERRED TO A FREE SCOPE**

## Exact live truth at wave start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Canonical tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed: **none**
- Latest merged PR: `#30`
- Latest exact verified feature head: `cf8b736a31647f5695211edf8d36b199bbe989ee`
- Verification OS: run `35660067501`, FAST job `106532947585` — **PASS** for that older exact feature head.
- Exact-current-main verification-os CI: **NOT_RUN**.
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- Production: **BLOCKED**.
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Collision audit

Recent branches ahead of the same canonical base were treated as active-looking and were not modified:

1. `docs/h7-provider-contract-reconciliation-20260922@760bca2ee67a5014f6438c442b7b9bb21f7aad61`
   - modifies `docs/governance/data_source_licenses.md` and its provider-contract checkpoint;
2. `fix/h7-adapter-provider-provenance-v1@042a135a5cda516ea3f8175bd06de60320f2649f`
   - modifies `historical_backfill_v2.py`, adds an adversarial provider-identity test and checkpoint;
3. `docs/h7-root-contract-reconciliation-20260922@741333f28091d0ebc003cc1e22f16b442baf1065`
   - modifies `AGENTS.md`, `GOAL.md` and its root-contract checkpoint.

This wave therefore changes only this isolated design/checkpoint document. It does not claim those scopes, open a PR, or trigger remote CI.

## Why implementation is intentionally deferred

Canonical main already has the right historical backbone:

`HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2 -> DurableManifest -> DatasetVersion`

and must not gain a second backfill architecture.

A direct networked Kraken adapter should **not** be rushed into the current seam yet because an important integration mismatch exists:

- `HistoricalAdapterV2.fetch_page(...)` and `BackfillRunnerV2.run(...)` are synchronous;
- the existing hardened public-provider transport (`MarketDataProvider._request_json`) is asynchronous;
- that transport enforces HTTPS/host allowlists, public-address DNS checks, GET-only policy by default, bounded responses, retries, no redirect following, `trust_env=False`, query-secret redaction and raw-payload hashing;
- bypassing it with a second ad-hoc `httpx`/`requests` client would duplicate security and provenance architecture;
- wrapping it with `asyncio.run()` inside the synchronous adapter would create nested-event-loop/runtime hazards and still would not return the raw bytes required by `BackfillPageV2.raw_payload`.

Therefore the safe implementation order is: **resolve the transport/raw-evidence seam once, then implement the provider adapter**.

## Official-source facts reviewed in this wave

### Kraken downloadable history

Official Kraken support material updated 2026-09-16 states that:

- downloadable historical trade CSVs contain the complete public trade history for each pair;
- downloadable OHLCVT CSVs exist for 1, 5, 15, 30, 60, 240, 720 and 1440 minute intervals;
- the files may be used in code and converted to other formats;
- the complete datasets available at the review date cover market history through 2026-06-30;
- missing OHLCVT rows mean no trades occurred in that interval; they must not silently be filled as observed candles.

Reviewed official sources:

- `https://support.kraken.com/articles/360047543791-downloadable-historical-market-data-time-and-sales-`
- `https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data`

### Kraken public REST market evidence

Current Kraken API documentation also exposes public read-only market evidence including:

- `GET /0/public/PostTrade`, with bounded pagination by `from_ts` / `to_ts`, a maximum count of 1000, ascending trade timestamps and `last_ts` continuation;
- `GET /0/public/PreTrade`, which returns top aggregated CLOB levels and per-level `publication_ts`.

These routes are potentially useful for bounded public smoke/microstructure evidence, but this document does **not** authorize a large retained corpus or infer redistribution rights.

## Canonical provider identity and quote law

The historical adapter must use identities that cannot be confused with another provider or quote currency:

- provider: `kraken_spot`
- source family: `kraken_public_market_data`
- XRP spot symbol: `XRP_USD`
- venue pair: Kraken's canonical XRP/USD representation at acquisition time
- instrument: `spot`
- USD observations remain USD; they may not be silently fused with Binance/KuCoin USDT observations.

The pending provider-identity guard branch should be reconciled before promotion so `page.receipt.provider == adapter.provider` is enforced before persistence.

## Adapter contract

The first Kraken historical implementation must extend the existing `HistoricalAdapterV2` seam rather than introducing a new runner/store.

Required invariants:

1. `provider`, `dataset` and `schema_version` are immutable adapter identity inputs and participate in `BackfillRunnerV2.job_key()`.
2. Every `BackfillPageV2.raw_payload` is the exact bounded byte sequence whose SHA-256 is in the page receipt.
3. Every observation references exactly that receipt via `fetch_id`, `payload_sha256`, `provider`, `source_id` and `fetched_at`.
4. Request fingerprints are computed from a canonical request descriptor, never from secrets; public Kraken market routes require no credentials in this scope.
5. Pagination cursor state is deterministic JSON and strictly progresses; replaying the same approved raw input produces identical observations/partition keys.
6. Rows outside `BackfillWindowV2` are rejected or deterministically excluded; no page may smuggle observations beyond the declared window.
7. Timestamps are timezone-aware UTC.
8. `observed_at` is the provider event/candle time, not fetch time.
9. `available_at` must represent defensible information availability. It must not be fabricated from `fetched_at` merely to pass a PIT gate.
10. Retrospective provider history acquired after the prediction time is **not** `STRICT_REPLAY`; it is `RECONSTRUCTED_PIT` only with a durable `reconstruction_basis_id`, otherwise `INELIGIBLE`.
11. Missing Kraken OHLCVT intervals are represented as missing evidence, not fabricated zero-volume/forward-filled observed candles.
12. Current/incomplete candles are excluded from historical closed-candle datasets.
13. Provider parse errors, ambiguous pair resolution, non-finite numerics, duplicate logical rows with conflicting values and schema drift fail closed.
14. No trading, order, account, funding, custody, wallet, leverage or private endpoint may be reachable from this adapter.
15. No paid API call is required or permitted merely to obtain evidence for this gate.

## Raw-evidence transport seam: required bounded precursor

Before a networked provider-specific historical adapter is promoted, implement **one** reusable raw-evidence request primitive on the existing hardened provider transport rather than a new HTTP stack.

Preferred shape:

- keep `_request_json()` behaviour backward compatible;
- factor or add a protected bounded GET helper that can return:
  - parsed JSON when applicable;
  - exact raw response bytes;
  - payload SHA-256;
  - latency;
  - a fetch timestamp captured at the transport boundary;
  - a sanitized canonical request URI/fingerprint input;
- retain existing host/method/DNS/size/retry/no-redirect/secret-redaction controls;
- add no order/private endpoint capability;
- require injected transport in hermetic tests;
- do not introduce a second HTTP client implementation for historical data.

If this cannot be achieved without materially widening `MarketDataProvider`, use an explicit ADR before introducing a new transport abstraction. Do not silently fork the networking architecture.

## Recommended first implementation shape

After the active provenance/contract scopes are reconciled, use one of these two evidence paths, in order:

### A. Deterministic local/archive parser first

Implement a Kraken OHLCVT parser/adapter over an explicitly supplied bounded raw byte payload or approved local artifact. This validates parser, receipt, temporal and DatasetVersion semantics without live-network nondeterminism or large retention.

This is the safest first code wave.

### B. Tiny public smoke fetch second

Only after the raw-evidence transport seam is green, add a tiny bounded unauthenticated Kraken public smoke fetch. It must remain ephemeral under the current governance gate unless retention is explicitly approved.

A large retained backfill remains **BLOCKED**.

## Minimum test matrix before promotion

### Determinism / parsing

- same raw bytes + same metadata -> identical receipt/observation hashes;
- row order normalization is explicit and deterministic;
- duplicate identical rows are handled deterministically;
- conflicting duplicate rows fail closed;
- malformed CSV/JSON rows fail closed;
- NaN/Inf numeric values fail closed;
- unsupported pair or interval fails closed;
- incomplete/current candle is excluded;
- no-trade interval is not fabricated.

### Provenance

- adapter provider mismatch vs receipt provider fails before persistence;
- receipt payload digest mismatch fails before persistence;
- observation `fetch_id`, provider, source, digest and fetch time must match its receipt;
- canonical URI contains no credentials;
- request fingerprint is stable for semantically identical requests;
- raw bytes persisted/processed match the advertised digest.

### Temporal / PIT

- future-fetched retrospective history cannot become `STRICT_REPLAY`;
- `RECONSTRUCTED_PIT` requires `reconstruction_basis_id`;
- unknown availability becomes `INELIGIBLE`;
- date/window boundaries are exact and UTC;
- observation timestamps cannot leak data outside the declared window.

### Security

- only allowlisted public Kraken host(s);
- only GET for this scope;
- redirects are not followed;
- non-public DNS results fail closed;
- oversized payload fails closed;
- transport exceptions do not expose query content/secrets;
- no account/private/order paths exist in the adapter surface.

### Source independence

- Kraken USD identity remains distinct from Binance USDT;
- provider universe counts venue/source identities, not duplicated/copy-derived feeds;
- one Kraken series cannot satisfy a multi-provider independent-source gate by itself.

## Code / security / QA review for this wave

- CODE REVIEW: **PASS** — documentation/design only; no runtime or model code changed.
- SECURITY REVIEW: **PASS** — no credentials, keys, account endpoints, orders, wallet/custody, leverage or network capability added.
- TEMPORAL / PROVENANCE REVIEW: **PASS** — fail-closed `STRICT_REPLAY` / `RECONSTRUCTED_PIT` / `INELIGIBLE` law is preserved and made explicit for the adapter.
- ARCHITECTURE REVIEW: **PASS** — reuses the existing backfill/store/provider foundations and explicitly rejects a parallel HTTP/backfill architecture.
- COLLISION REVIEW: **PASS for observed remote scopes** — provider-contract, provider-guard and root-contract branches were left untouched.
- Runtime tests: **NOT_RUN / N/A** for documentation-only scope.
- Exact branch FAST: **NOT_RUN** by design; no PR was opened merely to create CI activity.
- DEEP: **NOT_RUN**.
- RELEASE: **NOT_RUN**.

## Blockers / resume conditions

`KRAKEN_HISTORICAL_ADAPTER_PROMOTION = BLOCKED` until all of the following are true:

1. active provider-contract and provider-provenance branches are reconciled/promoted or explicitly abandoned;
2. owner retention acceptance required by the licence register is recorded for any retained real corpus;
3. the raw-evidence transport seam is implemented without duplicating the hardened provider transport, or an explicit ADR approves an alternative;
4. deterministic parser/fixture tests pass;
5. provenance/provider-binding/PIT tests pass;
6. repository manifest is regenerated from the exact candidate tree;
7. one bounded canonical FAST run is used only when a real promotion candidate exists;
8. production remains **BLOCKED** until all later scientific/operational gates pass.

## Next action

On the next cold start:

1. re-read `main`, open PRs and the three active-looking H7 branches;
2. do not duplicate them;
3. if the provider/provenance scopes are still active, prefer a disjoint raw-evidence transport design/implementation scope only if no newer writer owns it;
4. otherwise reconcile the provider-identity guard first, then implement the deterministic Kraken raw parser/adapter on the canonical seam;
5. only after retention approval materialize a tiny real DatasetVersion and run matched H6 B0-B4 versus H7 regime/analog OOS evidence;
6. preserve negative scientific outcomes exactly as observed.
