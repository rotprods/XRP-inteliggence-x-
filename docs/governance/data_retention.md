# Data-Retention Policy

Retention is constrained by source terms, reproducibility and minimisation.

| Data class | Default retention | Notes |
|---|---|---|
| Source code and manifests | Indefinite | Git history and signed/reviewed release evidence |
| Raw public-provider payloads | 30 days until licence approval | Prefer content-addressed encrypted object storage; never Git |
| Raw payload hashes and provenance envelopes | Indefinite | Supports audit without redistributing source payloads |
| Normalized market observations | Source-contract dependent | Versioned dataset partitions; never silently rewrite |
| Derived features and regime snapshots | Indefinite | Include model/config/dataset digests |
| Provider health and incident logs | 13 months | Secret-redacted and access-controlled |
| Demo fixtures | Indefinite | Clearly marked synthetic |
| CI artifacts | 30 days for alpha | Release artifacts promoted separately |
| Personal financial information | Not collected | Outside this repository's scope |

Deletion must preserve a tombstone containing dataset identifier, reason, time, owner and
previous checksum. Revised macro data creates a new dataset version rather than overwriting
point-in-time records.
