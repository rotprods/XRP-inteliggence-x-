# /Graphify — Provenance-first pipeline

## North Star

Transform heterogeneous XRP/financial/geopolitical research into an auditable temporal knowledge graph without allowing narrative density to masquerade as evidence.

## Pipeline

1. **Acquire** — read-only source retrieval; preserve canonical URI/API endpoint and retrieval timestamp.
2. **Hash** — SHA-256 raw payload/document where legally and technically possible.
3. **Normalize** — MIME/schema/encoding, canonical entity aliases, UTC timestamps.
4. **Atomize claims** — split prose into minimal propositions; never embed an entire article as one truth unit.
5. **Entity resolution** — stable IDs; aliases never imply identity without evidence.
6. **Temporal normalization** — distinguish `event_at`, `observed_at`, `published_at`, `available_at`, `retrieved_at`.
7. **Relation extraction** — typed edges only; store source span/pointer and direction.
8. **Evidence scoring** — source authority, primary status, independent corroboration, specificity, temporal validity.
9. **Contradiction graph** — link mutually incompatible claims and preserve both until resolved.
10. **Causal-hypothesis graph** — mechanism-labelled hypotheses separate from factual relations.
11. **COS20 projection** — compute/review the 20-dimensional analytical coordinates.
12. **Chunk + embed** — document, claim, entity and edge representations; version embedding model.
13. **Persist** — canonical graph/claim manifests in Git-compatible text; Qdrant as reconstructible derivative.
14. **Retrieve** — hybrid dense+sparse plus payload filters, graph neighborhood and temporal constraints.
15. **Answer** — cite provenance; explicitly return `NO_DATA` where evidence is absent/conflicting.
16. **Evaluate** — retrieval precision, contradiction recall, temporal leakage tests, source-substitution tests.

## Evidence contract

```yaml
claim_id: claim:sha256:<digest>
statement: "atomic proposition"
status: CLAIM_ONLY
confidence: 0.0
source_ids: []
independent_corroboration_count: 0
event_at: null
observed_at: null
published_at: null
available_at: null
retrieved_at: null
contradicts: []
supports: []
quality_flags: []
```

`confidence` is evidence confidence, not market-direction probability.

## Source tiers

- `T0_PRIMARY_MACHINE`: official API/ledger/court/legislation raw record.
- `T1_PRIMARY_DOCUMENT`: regulator, central bank, company/network official publication.
- `T2_HIGH_QUALITY_SECONDARY`: reputable reporting/research used for context and discovery.
- `T3_SECONDARY`: commentary/analysis requiring corroboration.
- `T4_SOCIAL_CLAIM`: social post/riddle/unverified assertion.

No T4 claim can become FACT solely from another T4 source.

## Narrative quarantine

Mr Pool, Bearable Guy, 589, Red October, gematria, numerology and similar material are useful as a **prediction/narrative dataset**. They require ex-ante timestamp, frozen interpretation, explicit target/horizon and resolution rule before evaluation. Post-hoc reinterpretation creates `HINDSIGHT_BIAS`; selecting only successful riddles creates `SURVIVORSHIP_BIAS`; vague claims create `NON_FALSIFIABLE`.

Claims about secret ethnic/religious control, ritual blood/adrenochrome or universal hidden coordination are represented only as claims unless primary evidence supports a narrowly stated proposition. Ethnicity/religion is never itself a causal financial edge.

## Market boundary

Market time-series data is not stored primarily as embeddings. OHLCV, trades, order books, OI, funding, basis and macro observations remain structured point-in-time evidence. Semantic state documents may reference immutable snapshot IDs.

## Fail-closed retrieval

A query requiring live/point-in-time truth returns `NO_DATA` when freshness, provider agreement, temporal availability or provenance requirements fail. Retrieval must never fill gaps with nearest-neighbor prose.
