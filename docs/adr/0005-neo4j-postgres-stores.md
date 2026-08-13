# ADR-0005: Neo4j for the knowledge graphs, Postgres for app state

**Status:** Accepted (2026-08-13). Supersedes ADR-0001.

## Context

ADR-0001 kept both graphs in process, built from committed JSON, with file writes for
member data. Two forces broke it. Railway's filesystem is ephemeral, so file writes do
not survive a deploy. And the standing product principle changed: the system must
demonstrate, at small scale, the mechanism that works at production scale — a massive
knowledge base traversed in its store, not loaded into each process.

## Decision

- **Neo4j** holds both knowledge graphs (KG1 and KG2). Traversals run in the store as
  parameterized Cypher. The safety walk returns a path; that path is the provenance
  trace. Python applies the verdict matrix over returned paths.
- **Postgres** holds app state: LangGraph threads and checkpoints
  (langgraph-checkpoint-postgres).
- The provided JSON files are **seed data, not the store**. A two-stage pipeline
  ingests them: *acquire* writes versioned snapshot artifacts (the NCI EVS fetch, the
  subset of ADR/GNT-214 unchanged); *ingest* MERGEs idempotently into Neo4j, keyed on
  stable IDs, stamping `source`, `version`, `ingested_at` on every node. It runs as
  `pnpm seed` locally, a pre-deploy step on Railway, and a CI step before tests.
- **Neo4j is the system of record for KG2.** A confirmed coach action is one Cypher
  transaction stamped with actor and timestamp. No dual store, no sync job.
- Locally, docker compose boots Neo4j and Postgres. CI uses service containers.

## Consequences

- Traversal tests need a seeded store; the pure-function-only test story of ADR-0001 is
  gone. This is the accepted price of demonstrating storage-backed traversal.
- The schema vocabulary of GNT-216 survives: node types become Neo4j labels, edge types
  become relationship types. The seven copilot read tools become named Cypher queries.
- A new ontology is a new acquire fetcher emitting the same node/edge shape; ingest does
  not change.
- Rejected: Postgres + Apache AGE (niche, rough tooling); nodes/edges tables with
  recursive CTEs (demonstrates SQL, not graph traversal); event log with projections
  (over-engineering at this scope; revisit if replayable audit becomes a requirement).
