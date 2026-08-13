# ADR-0002: Deterministic safety floor; agent may tighten, never loosen

**Status:** Accepted (2026-08-13)

## Context

The PRD's core constraint: "Safety constraints must be enforced deterministically through
graph traversal, not left to a probabilistic prompt instruction." At the same time the
product is agentic — an LLM interprets coach input, composes plans, and reads soft context
(chat, adherence) that no graph edge adjudicates. The tension: where does the agent's
judgment end and the graph's authority begin? A pure agent-judged safety model was
seriously proposed and rejected.

## Decision

Safety verdicts (exclude | caution | clear, per exercise) are computed by a pure-function
graph traversal — the **safety floor**. The agent may **tighten** the floor (add caution or
exclusions based on context the graph can't see), never loosen it: nothing the traversal
excluded can re-enter a plan. Agent tightenings are recorded in the provenance trace as
agent decisions, distinct from graph decisions.

The traversal reads three knowledge layers, highest precedence first:

1. **Member clinical directives** — the clinician note on the member's injury record,
   parsed by the resolver into movement-pattern restrictions. Fully dynamic per member.
2. **Authored condition file** (`data/contraindications.json`) — Injury → MovementPattern
   edges with level (avoid | caution) for four conditions (patellofemoral pain syndrome,
   nonspecific low back pain, shoulder impingement, lateral ankle sprain). AI-drafted at
   build time, human-approved by PR; a citation to published clinical guidance is
   mandatory per row — ingestion rejects uncited rows. Never generated at runtime.
3. **SNOMED anatomical fallback** — any resolvable condition sites onto anatomy
   (findingSite → isA* → Joint), flagging every exercise loading that joint at caution.
   Breadth for thousands of conditions without authoring.

Status/severity modulation is escalation-only: active status or ≥ moderate severity
escalates caution → exclude; resolved drops to clear (kept in provenance); nothing softens.

## Consequences

- The safety filter is a unit-testable pure function (a PRD-mandated test target), and
  every verdict carries the graph path that produced it — the coach-facing trace is the
  walked path, not a reconstruction.
- The agent keeps real safety-relevant judgment (it can react to "knee felt achy
  yesterday") with one direction of error made structurally impossible.
- Coverage degrades to coarser, never to silent: unauthored conditions get anatomical
  caution, not nothing.
- Rejected: agent-judged safety (contradicts the PRD's core constraint; untestable;
  trace collapses to model narrative). Rejected: runtime LLM generation of
  contraindication knowledge (uncited safety claims; same determinism failure).
- Ceiling: four authored conditions. Scale path is more rows through the same
  cite-and-review gate, with LLM-assisted drafting kept behind human approval.
