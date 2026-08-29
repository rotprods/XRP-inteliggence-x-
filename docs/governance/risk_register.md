# Risk Register

Scoring: likelihood and impact are `1` (low) to `5` (critical). Risk score is their product.
The register is reviewed whenever a release gate changes.

| ID | Risk | L | I | Score | Current controls | Residual action / owner |
|---|---|---:|---:|---:|---|---|
| R-001 | Stale or conflicting market data produces a misleading regime | 4 | 5 | 20 | Multi-provider consensus, freshness flags, fail-closed output | Validate live providers regionally; Data engineer |
| R-002 | USD and USDT markets are silently conflated | 3 | 5 | 15 | Separate canonical symbols and provider mappings | Add stablecoin-basis policy before cross-quote fusion; Data engineer |
| R-003 | Synthetic/demo values leak into live execution | 3 | 5 | 15 | Explicit demo supplemental mapping and `SYNTHETIC` flag | Add live orchestrator contract tests; QA |
| R-004 | Macro revisions create future-data leakage | 4 | 5 | 20 | `observed_at` / `available_at` contracts | Build ALFRED/vintage store and replay tests; Quant researcher |
| R-005 | Expert score is presented as calibrated probability | 3 | 5 | 15 | Separate confidence semantics and `probability_calibrated=false` | Complete walk-forward calibration; Quant researcher |
| R-006 | Provider endpoint is abused for SSRF or secret exfiltration | 3 | 5 | 15 | HTTPS/host allowlists, public-IP resolution, no redirects, secret-safe errors | Repeat adversarial tests in CI and container; Security reviewer |
| R-007 | GitHub Actions amplification creates cost/noise and corrupts state | 3 | 4 | 12 | Exactly one manual verification workflow; workflows cannot author code | Keep WIP limits and remote circuit breaker; Orchestrator |
| R-008 | Manifest or release artifact does not match reviewed source | 3 | 4 | 12 | SHA-256 manifest and atomic release evidence | Compare remote tree to local manifest before merge; QA |
| R-009 | SQLite corruption or concurrent writes lose evidence | 3 | 4 | 12 | WAL, busy timeout, transactional writes, audit events | Add backup/restore drill and integrity checks; SRE |
| R-010 | News or corporate announcements are treated as token causality | 4 | 3 | 12 | Separate Ripple, XRPL, regulation and price evidence layers | Add materiality taxonomy and analyst annotation; Market analyst |
| R-011 | Source terms prohibit retention or redistribution | 3 | 4 | 12 | Licence register and metadata-only defaults | Legal/licence review before persistent backfill; Project owner |
| R-012 | Model weights drift without traceability | 3 | 4 | 12 | Versioned JSON config and ADRs | Add config digest to every snapshot; Quant researcher |
| R-013 | Live alert influences financial decisions before validation | 3 | 5 | 15 | Engineering alpha banner, output block, no trading integration | 30-day immutable shadow gate; Project owner |
| R-014 | Dependency compromise affects data or build integrity | 2 | 5 | 10 | Minimal dependencies and manual security workflow | Add lockfile, SBOM and dependency audit; Security reviewer |
