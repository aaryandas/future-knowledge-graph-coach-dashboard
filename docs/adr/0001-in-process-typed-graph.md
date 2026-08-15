# ADR-0001: In-process typed graph, no graph database

**Status:** Superseded by ADR-0005 (2026-08-13)

## Context

The product is built around two knowledge graphs (movement/clinical reference data;
per-member context). An obvious reading of "knowledge graph project" reaches for Neo4j or
another graph database. The dataset is ~1,000 nodes total (53 exercises, ~100 taxonomy
nodes, ~350 SNOMED snapshot concepts, one member's context), fully known at build time,
with shallow traversals (2–4 hops). The PRD requires one-command local run, a ~5s AI
latency budget, and unit-tested deterministic safety traversal.

## Decision

Both graphs are hand-rolled in-process typed structures, built at boot from committed JSON.
No graph database, embedded or server. KG2 access goes through a narrow per-member accessor
(`getMemberContext(memberId)`) so the storage of the growing side is swappable in one place.

## Consequences

- Traversals are pure functions in the app's language — unit-testable with zero
  infrastructure, which the PRD's mandated safety-filter tests need.
- One-command run keeps zero external dependencies; no Docker, seed step, or startup
  ordering.
- No ad-hoc query language: copilot retrievals are named functions, not Cypher (better for
  grounding; less flexible for exploration).
- Scale story (documented, not built): KG1 is read-only reference data that stays
  in-process even at production scale — you replicate it into the serving tier, not move it
  out. KG2 is the part that grows and is partitioned per member; at scale it becomes rows
  behind the same accessor, not a graph workload — no product traversal crosses members.
- Rejected: Neo4j (server + ops against a graded one-command run), embedded graph DB / Kùzu
  (a query language between the tests and the logic, for no traversal we can't write as a
  function at this scale).
