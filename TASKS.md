# TASKS — Master Work Breakdown

Legend: `[x]` completed in this package, `[~]` partially implemented/scaffolded, `[ ]` requires live data, credentials, validation or GitHub access.

## Q1 — Verification & CI Excellence OS

Legend for Q1: `[x]` locally implemented and evidenced, `[~]` implemented but requires clean remote tooling/evidence, `[ ]` not yet executed.

- [x] Q1.0 — Lock cost + source of truth.
- [x] Q1.1 — Persist canonical `docs/verification/VERIFICATION_OS.md`.
- [x] Q1.2 — Build hermetic pytest architecture and deny unexpected network.
- [x] Q1.3 — Enforce risk-tiered global/critical/changed-line coverage gates.
- [~] Q1.4 — Add Hypothesis property suite; clean-runner execution pending because local recovery runtime lacks Hypothesis.
- [x] Q1.5 — Build provider contract gauntlet for Binance/Coinbase/Kraken/KuCoin/FRED/XRPL.
- [x] Q1.6 — Build temporal correctness gauntlet.
- [x] Q1.7 — Add point-in-time leakage protection, rolling window and embargo semantics.
- [x] Q1.8 — Add SQLite transaction/corruption/backup/restore/resource fault suite.
- [x] Q1.9 — Add API contract/degraded/no-data suite.
- [x] Q1.10 — Expand adversarial SSRF/DNS/payload/secret/RPC security tests.
- [~] Q1.11 — Configure mutmut 3 mutation gate and score parser; controlled release run pending.
- [~] Q1.12 — Final `0.2.0a2` reproducible wheel PASS (`4e6a21a17d04…`); SBOM/audit and clean dependency-resolving install remain clean-runner gates.
- [~] Q1.13 — Configure Python 3.11/3.12/3.13 validation; clean-runner execution pending.
- [~] Q1.14 — Build one unified cost-bounded CI workflow; remote execution pending.
- [x] Q1.15 — Add deterministic test-order seed replay; three local engine-suite seeds PASS, deeper release replay remains controlled.
- [x] Q1.16 — Emit machine-readable quality evidence.
- [~] Q1.17 — Run adversarial review; surviving remote static/mutation findings must become regression tests.
- [ ] Q1.18 — Promote one clean Verification OS PR and reconcile remote tree hashes.
- [ ] Q1.19 — Configure `main` branch protection after CI stability.
- [ ] Q1.20 — Freeze Q1 gate only after Hypothesis/static/mutation/multi-Python/remote evidence all PASS.

### Q1 local evidence checkpoint

- deterministic tests: 238 PASS, one Hypothesis module skipped only because dependency is unavailable offline;
- application line coverage: 100%;
- application branch coverage: 100%;
- critical-module line/branch coverage: 100%;
- changed executable line coverage: 100%;
- paid API calls: 0;
- unexpected network calls: blocked by test harness;
- production readiness: BLOCKED by separate data/calibration/shadow/SRE gates.


## P0 — Governance and control plane

- [x] T-0001 — Confirm canonical repository and default branch
- [x] T-0002 — Record target GitHub repository URL
- [x] T-0003 — Define project owner and reviewer roles
- [x] T-0004 — Lock North Star and non-goals
- [x] T-0005 — Create ADR register
- [x] T-0006 — Create risk register
- [x] T-0007 — Create data-source licence register
- [x] T-0008 — Create secrets inventory without storing secret values
- [x] T-0009 — Define release gates
- [x] T-0010 — Define incident severity levels
- [x] T-0011 — Define data-retention policy
- [x] T-0012 — Define change-control workflow
- [x] T-0013 — Define handoff template
- [x] T-0014 — Define rollback standard
- [x] T-0015 — Define production readiness checklist

## P1 — Repository and engineering baseline

- [x] T-0016 — Create Python package layout
- [x] T-0017 — Configure pyproject metadata
- [x] T-0018 — Configure linting
- [x] T-0019 — Configure type checking
- [x] T-0020 — Configure pytest
- [x] T-0021 — Create deterministic fixtures
- [x] T-0022 — Create Makefile
- [x] T-0023 — Create Dockerfile
- [x] T-0024 — Create docker-compose stack
- [x] T-0025 — Create environment template
- [x] T-0026 — Create CI workflow
- [x] T-0027 — Create security policy
- [x] T-0028 — Create contribution guide
- [x] T-0029 — Create changelog
- [x] T-0030 — Create version module
- [x] T-0031 — Create structured logging
- [x] T-0032 — Create CLI entry point
- [x] T-0033 — Create FastAPI application
- [x] T-0034 — Create health endpoint
- [x] T-0035 — Create build manifest generator

## P2 — Canonical data model

- [x] T-0036 — Define AssetObservation schema
- [x] T-0037 — Define Candle schema
- [x] T-0038 — Define DerivativesSnapshot schema
- [x] T-0039 — Define LedgerMetric schema
- [x] T-0040 — Define NewsEvent schema
- [x] T-0041 — Define ProviderHealth schema
- [x] T-0042 — Define FeatureSnapshot schema
- [x] T-0043 — Define RegimeSnapshot schema
- [x] T-0044 — Define AlertEvent schema
- [x] T-0045 — Define provenance fields
- [x] T-0046 — Define freshness taxonomy
- [x] T-0047 — Define data-quality flags
- [x] T-0048 — Define unit normalization
- [x] T-0049 — Define timezone policy
- [x] T-0050 — Define symbol registry
- [x] T-0051 — Define interval registry
- [x] T-0052 — Define missing-value policy
- [x] T-0053 — Define revision policy
- [x] T-0054 — Publish JSON Schemas
- [x] T-0055 — Add schema compatibility tests

## P3 — Spot crypto ingestion

- [x] T-0056 — Implement provider base class
- [x] T-0057 — Implement HTTP retry policy
- [x] T-0058 — Implement rate-limit awareness
- [x] T-0059 — Implement Binance spot candles
- [x] T-0060 — Implement Binance spot ticker
- [x] T-0061 — Implement Coinbase candles
- [x] T-0062 — Implement Coinbase ticker
- [x] T-0063 — Implement Kraken OHLC
- [x] T-0064 — Implement Kraken ticker
- [x] T-0065 — Implement provider response validation
- [x] T-0066 — Implement symbol translation
- [x] T-0067 — Implement timestamp normalization
- [x] T-0068 — Implement provider consensus price
- [x] T-0069 — Implement outlier rejection
- [x] T-0070 — Implement stale-data rejection
- [x] T-0071 — Implement fallback routing
- [x] T-0072 — Persist raw payload hashes
- [x] T-0073 — Add adapter contract tests
- [ ] T-0074 — Run regional availability test
- [x] T-0075 — Document public endpoint limitations

## P4 — Derivatives ingestion

- [~] T-0076 — Implement open-interest adapter
- [~] T-0077 — Implement funding-rate adapter
- [ ] T-0078 — Implement futures basis adapter
- [ ] T-0079 — Implement liquidations adapter
- [ ] T-0080 — Implement long-short ratio adapter
- [ ] T-0081 — Implement taker imbalance adapter
- [ ] T-0082 — Normalize contract units
- [ ] T-0083 — Normalize inverse and linear contracts
- [ ] T-0084 — Detect exchange maintenance
- [ ] T-0085 — Detect leverage-driven price expansion
- [ ] T-0086 — Compute OI-price divergence
- [ ] T-0087 — Compute funding z-score
- [ ] T-0088 — Compute liquidation impulse
- [ ] T-0089 — Compute basis stress
- [ ] T-0090 — Add derivatives quality score
- [ ] T-0091 — Add provider failover
- [ ] T-0092 — Add paid-vendor interface
- [ ] T-0093 — Document unavailable metrics
- [ ] T-0094 — Validate against exchange UI samples
- [ ] T-0095 — Create derivatives incident drill

## P5 — Macro, equities and commodities

- [x] T-0096 — Implement FRED series adapter
- [~] T-0097 — Implement point-in-time vintage support
- [ ] T-0098 — Register 2Y Treasury yield
- [ ] T-0099 — Register 10Y Treasury yield
- [ ] T-0100 — Register 30Y Treasury yield
- [ ] T-0101 — Register real-yield proxy
- [ ] T-0102 — Register broad dollar index proxy
- [ ] T-0103 — Register financial-conditions proxy
- [ ] T-0104 — Register money/liquidity proxies
- [ ] T-0105 — Register S&P 500
- [ ] T-0106 — Register Nasdaq 100
- [ ] T-0107 — Register VIX
- [ ] T-0108 — Register Coinbase equity
- [ ] T-0109 — Register Strategy equity
- [ ] T-0110 — Register crypto-miner basket
- [ ] T-0111 — Register gold
- [ ] T-0112 — Register WTI
- [ ] T-0113 — Register Brent
- [ ] T-0114 — Register gasoline
- [ ] T-0115 — Register natural gas
- [ ] T-0116 — Register cocoa as zero-weight exploratory series
- [ ] T-0117 — Align trading calendars
- [ ] T-0118 — Forward-fill only where economically valid
- [ ] T-0119 — Add market-holiday handling
- [ ] T-0120 — Add macro release calendar
- [ ] T-0121 — Add revision-aware backtest tests

## P6 — XRP/Ripple/XRPL intelligence

- [x] T-0122 — Implement XRPL server-info adapter
- [ ] T-0123 — Implement ledger-close metrics
- [ ] T-0124 — Implement transaction-count metrics
- [ ] T-0125 — Implement fee metrics
- [ ] T-0126 — Implement DEX book metrics
- [ ] T-0127 — Implement AMM metrics
- [ ] T-0128 — Implement trust-line metrics
- [ ] T-0129 — Implement active-account proxy
- [ ] T-0130 — Implement whale-account watchlists with provenance
- [ ] T-0131 — Implement exchange flow labels only from verified sources
- [ ] T-0132 — Implement RLUSD supply/activity metrics
- [ ] T-0133 — Implement Ripple announcement RSS ingestion
- [ ] T-0134 — Implement SEC event ingestion
- [ ] T-0135 — Implement SWIFT event ingestion
- [ ] T-0136 — Separate company events from token-utility metrics
- [ ] T-0137 — Create event materiality taxonomy
- [ ] T-0138 — Create event decay functions
- [ ] T-0139 — Create duplicate-news suppression
- [ ] T-0140 — Create source trust score
- [ ] T-0141 — Add manual analyst annotation workflow
- [ ] T-0142 — Link Sovereign Escape OS XRP forensics context

## P7 — Feature engineering

- [x] T-0143 — Compute multi-horizon returns
- [x] T-0144 — Compute realized volatility
- [ ] T-0145 — Compute ATR proxy
- [x] T-0146 — Compute RSI
- [x] T-0147 — Compute moving-average distance
- [x] T-0148 — Compute maximum drawdown
- [ ] T-0149 — Compute trend persistence
- [ ] T-0150 — Compute volume z-score
- [x] T-0151 — Compute XRP/BTC relative strength
- [x] T-0152 — Compute ETH/BTC rotation
- [ ] T-0153 — Compute BTC-dominance change
- [x] T-0154 — Compute cross-asset rolling correlation
- [x] T-0155 — Compute beta to BTC
- [x] T-0156 — Compute beta to Nasdaq
- [ ] T-0157 — Compute DXY sensitivity
- [ ] T-0158 — Compute yield sensitivity
- [ ] T-0159 — Compute energy-inflation pressure
- [ ] T-0160 — Compute stablecoin liquidity proxy
- [ ] T-0161 — Compute breadth proxy
- [x] T-0162 — Compute data coverage
- [x] T-0163 — Compute source agreement
- [x] T-0164 — Compute freshness decay
- [x] T-0165 — Add robust scaling
- [ ] T-0166 — Winsorize only inside training windows
- [x] T-0167 — Prevent future-data leakage

## P8 — Regime and probability engine

- [x] T-0168 — Define regime taxonomy
- [x] T-0169 — Define score components
- [x] T-0170 — Define initial expert weights
- [x] T-0171 — Implement macro score
- [x] T-0172 — Implement crypto score
- [x] T-0173 — Implement XRP relative-strength score
- [x] T-0174 — Implement derivatives-health score
- [ ] T-0175 — Implement XRPL activity score
- [x] T-0176 — Implement squeeze-risk score
- [x] T-0177 — Implement distribution-risk score
- [x] T-0178 — Implement bear-risk score
- [x] T-0179 — Implement confidence score
- [x] T-0180 — Implement missing-data degradation
- [x] T-0181 — Implement conflict penalties
- [x] T-0182 — Implement horizon-specific weights
- [x] T-0183 — Implement regime classifier
- [x] T-0184 — Implement key-driver attribution
- [x] T-0185 — Implement invalidation generator
- [ ] T-0186 — Implement threshold sensitivity analysis
- [~] T-0187 — Implement probability calibration
- [x] T-0188 — Create model card
- [x] T-0189 — Create challenger-model interface
- [x] T-0190 — Block production output below confidence threshold

## P9 — Historical research and backtesting

- [ ] T-0191 — Backfill BTC history
- [ ] T-0192 — Backfill XRP history
- [ ] T-0193 — Backfill ETH history
- [ ] T-0194 — Backfill macro history
- [ ] T-0195 — Backfill equity history
- [ ] T-0196 — Backfill commodity history
- [ ] T-0197 — Backfill derivatives where available
- [ ] T-0198 — Create 2017 XRP event window
- [ ] T-0199 — Create 2018 capitulation window
- [ ] T-0200 — Create 2020 SEC event window
- [ ] T-0201 — Create 2021 bull window
- [ ] T-0202 — Create 2022 liquidity/credit shock window
- [ ] T-0203 — Create 2023 legal-repricing window
- [ ] T-0204 — Create 2024-2025 institutional window
- [ ] T-0205 — Create 2026 correction/reversal window
- [x] T-0206 — Implement expanding-window validation
- [ ] T-0207 — Implement rolling-window validation
- [ ] T-0208 — Implement embargo gaps
- [ ] T-0209 — Implement class-balance analysis
- [x] T-0210 — Compute Brier score
- [ ] T-0211 — Compute calibration curve
- [x] T-0212 — Compute directional accuracy
- [ ] T-0213 — Compute precision by regime
- [ ] T-0214 — Compute max adverse excursion
- [ ] T-0215 — Compute false-alert rate
- [ ] T-0216 — Run ablation tests
- [ ] T-0217 — Run weight stability tests
- [ ] T-0218 — Run provider substitution tests
- [ ] T-0219 — Document survivorship and revision limitations
- [ ] T-0220 — Publish reproducible report

## P10 — API, dashboard and alerts

- [x] T-0221 — Expose latest XRP regime endpoint
- [x] T-0222 — Expose horizon endpoint
- [x] T-0223 — Expose provider-health endpoint
- [x] T-0224 — Expose feature explanation endpoint
- [ ] T-0225 — Expose historical analogue endpoint
- [ ] T-0226 — Expose audit endpoint
- [x] T-0227 — Create JSON response contract
- [~] T-0228 — Create dashboard wireframe
- [ ] T-0229 — Create regime timeline
- [ ] T-0230 — Create driver waterfall
- [ ] T-0231 — Create provider freshness panel
- [ ] T-0232 — Create cross-asset heatmap
- [ ] T-0233 — Create support/resistance panel
- [x] T-0234 — Create alert-rule registry
- [x] T-0235 — Create webhook adapter
- [ ] T-0236 — Create email adapter boundary
- [ ] T-0237 — Create Telegram/Slack boundary
- [x] T-0238 — Add alert deduplication
- [x] T-0239 — Add cooldowns
- [ ] T-0240 — Add acknowledgement state
- [ ] T-0241 — Add escalation policy
- [ ] T-0242 — Add daily report generator
- [ ] T-0243 — Add weekly regime report
- [ ] T-0244 — Add incident banner
- [ ] T-0245 — Add no-data state
- [ ] T-0246 — Add mobile-friendly summary

## P11 — SRE, security and production

- [x] T-0247 — Create scheduler
- [x] T-0248 — Create idempotent jobs
- [ ] T-0249 — Create job locks
- [ ] T-0250 — Create retry queues
- [ ] T-0251 — Create dead-letter records
- [ ] T-0252 — Create metrics endpoint
- [x] T-0253 — Create structured audit log
- [ ] T-0254 — Create freshness SLOs
- [ ] T-0255 — Create provider availability SLOs
- [ ] T-0256 — Create snapshot latency SLO
- [~] T-0257 — Create backup policy
- [~] T-0258 — Create restore drill
- [~] T-0259 — Create schema migration workflow
- [ ] T-0260 — Create secret-rotation procedure
- [~] T-0261 — Apply least privilege
- [~] T-0262 — Disable trading scopes
- [ ] T-0263 — Add dependency scanning
- [~] T-0264 — Add static analysis
- [ ] T-0265 — Add container scan
- [ ] T-0266 — Add SBOM generation
- [x] T-0267 — Create threat model
- [x] T-0268 — Test SSRF protections
- [x] T-0269 — Test log redaction
- [x] T-0270 — Test malformed provider payloads
- [x] T-0271 — Test clock skew
- [ ] T-0272 — Test partial outage
- [x] T-0273 — Test conflicting prices
- [ ] T-0274 — Test stale macro data
- [x] T-0275 — Test database corruption recovery
- [ ] T-0276 — Sign release manifest

## P12 — GitHub migration and PR

- [x] T-0277 — Confirm target repository
- [x] T-0278 — Identify default branch
- [x] T-0279 — Inspect existing architecture
- [x] T-0280 — Map existing files to canonical structure
- [x] T-0281 — Avoid parallel duplicate modules
- [x] T-0282 — Create feature branch
- [x] T-0283 — Apply source bundle
- [~] T-0284 — Run formatting
- [x] T-0285 — Run tests
- [~] T-0286 — Run type checks
- [~] T-0287 — Run security checks
- [x] T-0288 — Generate migration notes
- [~] T-0289 — Generate compatibility report
- [~] T-0290 — Create draft PR
- [ ] T-0291 — Attach architecture diagram
- [ ] T-0292 — Attach backtest evidence
- [ ] T-0293 — Attach data-source register
- [ ] T-0294 — Request review
- [ ] T-0295 — Resolve review threads
- [ ] T-0296 — Re-run CI
- [x] T-0297 — Update release gate
- [ ] T-0298 — Merge only after evidence
- [ ] T-0299 — Tag alpha release
- [ ] T-0300 — Write Drive handoff with branch, SHA and PR URL

**Total tasks:** 300

## Immediate critical path

1. Promote the locally verified foundation onto one clean GitHub branch based on remote `main`.
2. Run the single bounded manual quality workflow and resolve Ruff, mypy and Bandit findings.
3. Open one clean draft PR and merge only after evidence and review.
4. Configure read-only live-data access and validate providers regionally.
5. Complete point-in-time historical backfill and leakage-safe walk-forward research.
6. Operate immutable shadow mode for 30 days before any production decision use.
