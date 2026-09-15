# XRP SemanticBrain — Graphify + COS 20D

Status: `RESEARCH_DERIVED / SHADOW_ONLY / NO_EXECUTION`

This subtree converts the XRP intelligence research corpus into a provenance-first graph/vector knowledge plane. It is intentionally subordinate to the repository's existing data-quality, point-in-time, calibration and release gates.

## Invariants

1. Qdrant is a **derived, reconstructible retrieval index**, never source-of-truth.
2. Facts, observations, inferences, hypotheses, claims and narratives remain distinct.
3. `CLAIM_ONLY`, `DISPUTED`, `REFUTED` and `NO_DATA` material cannot be promoted to `FACT` by embedding similarity, graph centrality, repetition, numerology, virality or hindsight.
4. Every external datum carries provenance and temporal availability.
5. Market observations require provider identity; production-grade critical price consensus still requires independent providers.
6. Narrative intelligence (Mr Pool, Bearable Guy, 589, Red October, gematria, etc.) is isolated from execution weight until a timestamped, leakage-safe out-of-sample evaluation demonstrates predictive value.
7. No trading, custody, wallet signing, withdrawals or private-key handling.

## Components

- `COS20D_SPEC.md` — twenty-dimensional analytical coordinate system.
- `GRAPHIFY_SPEC.md` — ingestion, entity/claim/relation extraction and evidence promotion pipeline.
- `QDRANT_SCHEMA.json` — hybrid semantic index contract.
- `KNOWLEDGE_MANIFEST.yaml` — corpus domains, source tiers and reconstruction contract.
- `RESEARCH_2026-09-15.md` — distilled evidence map from the September 2026 advanced-research wave.

## Retrieval architecture

`raw evidence -> normalized document -> atomic claims -> entities/typed temporal edges -> contradiction/evidence graph -> COS20D coordinates -> dense+sparse retrieval -> answer with provenance`

Structured OHLCV/order-book/derivatives data remains in a time-series/relational evidence plane. Qdrant stores semantic state representations and document/claim/entity chunks; it does not replace point-in-time market storage.
