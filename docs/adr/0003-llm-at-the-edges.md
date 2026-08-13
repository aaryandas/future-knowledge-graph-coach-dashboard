# ADR-0003: LLM at the edges; generation is a deterministic pipeline

**Status:** Accepted (2026-08-13)

## Context

The workout-generation runtime must be LangGraph (submission constraint), safety must come
from graph traversal rather than prompt instructions (PRD core constraint, ADR-0002), and
plans should render in roughly five seconds on a fast free-tier model. The obvious
LangGraph idiom — a tool-calling agent loop where the LLM invokes resolve/filter/pack as
tools — was seriously considered and rejected.

## Decision

The runtime is a deterministic pipeline expressed as a LangGraph StateGraph. The LLM sits
at exactly two edges:

1. **Interpretation** — one structured-output call turning the coach's message into an
   Intent of raw mention strings (never concept ids). The resolver grounds every mention;
   the LLM cannot hallucinate a graph concept into a plan.
2. **Annotation** — an optional post-plan call for coaching notes, which may tighten
   safety per ADR-0002 but never selects exercises. It streams after the plan is already
   rendered, so it is additive, never load-bearing.

Everything between the edges — resolution, safety verdicts, ranking, packing, substitution
pairing — is pure functions over the in-process graph. Interactive adjustments are parsed
by the same interpretation edge into deltas, merged into a session ConstraintSet held in
checkpointed thread state, and the pipeline re-runs from the full set; plans are never
patched in place and the LLM never edits a previous plan.

## Consequences

- Every LLM round-trip the loop idiom would spend is gone: one small blocking extraction
  call, then milliseconds of graph work — the plan and full trace ship inside the budget
  regardless of annotation latency.
- The model cannot skip the safety filter, because calling it is not the model's decision.
  A tool-loop reintroduces exactly the probabilistic-safety failure the PRD forbids.
- Determinism makes adjustment stability emergent: same ConstraintSet, same plan; one new
  exclusion changes one slot and its substitution line.
- The provenance trace accumulates in graph state as nodes run, so a replayed checkpoint
  replays the exact trace — the walked-path property extends to the whole runtime.
- Rejected: tool-calling agent loop (latency multiplication, skippable safety, trace
  becomes model narrative). Rejected: patching plans in place on adjustment (second code
  path that drifts from generation; a mid-session injury legitimately reshapes the whole
  plan).
- Ceiling: the interpretation edge is one call with one retry — a prompt the model cannot
  parse fails visibly rather than looping. If richer multi-turn negotiation is ever
  needed, it lands as more pipeline nodes, not a free-running loop.
