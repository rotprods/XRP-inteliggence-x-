# Migration Notes

This package uses SQLite and file-based JSON configuration to minimise integration assumptions. During migration:

- map the repository's existing settings and database abstractions;
- preserve existing symbol identifiers through an explicit translation layer;
- import no generated demo database into production;
- migrate schema through reviewed, reversible steps;
- keep the public API behind a versioned `/v1` boundary.
