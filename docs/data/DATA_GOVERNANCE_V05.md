# Data Governance v0.5

## Source approval is separate from technical access

A successful API response does not establish a licence, redistribution right or production approval. Every source must have:

- provider and domain;
- applicable terms URL;
- authentication model;
- internal-research determination;
- production-processing determination;
- redistribution determination;
- retention limit;
- review owner and review date.

The default state is `REVIEW_REQUIRED`. While any active source remains unresolved, the production release gate stays blocked.

## Separation of systems

The market engine may contain public market/macro data, source provenance, model features and immutable predictions. It must not contain:

- wallet seeds or private keys;
- exchange credentials with trading/withdrawal scope;
- personal holdings, tax identifiers or personal banking records;
- Sovereign Escape OS personal/fiscal context.

Personal context may reference exported read-only market snapshots through an explicit integration contract; it is not copied into the engine.

## Retention

Retention defaults are defined in `config/data_retention_v05.json`. Provider terms or law may shorten those defaults. Deletion of manifested raw or normalized data must be recorded and must not leave a manifest claiming bytes that no longer exist.

## Derived data

Derived indicators and model features still require source provenance. The engine must be able to answer:

```text
feature
  ↓
normalized records
  ↓
raw payload hashes
  ↓
provider, URL, timestamps and licence record
```

## Copyright and public events

For Ripple, SEC, Swift and other publication sources, persist links, metadata, materiality labels and short derived summaries. Do not ingest or redistribute complete copyrighted articles unless an explicit lawful basis has been recorded.

## Release gate

Engineering code may merge while licence reviews remain open, provided unresolved sources cannot be enabled as production sources. Production cannot pass until every enabled source has an approved record and enforceable retention policy.
