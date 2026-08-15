# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: a fitness/health coach working one member at a time. Morning ritual: log in
to a member, work the morning brief (celebrate wins, check-ins, churn-risk follow-ups),
generate or adjust that member's workout, and ask questions over their context. The
coach is time-pressed and safety-accountable — when someone asks "why this exercise?",
they need an audit trail, not a hunch.

Secondary (confirmed): hiring reviewers evaluating this take-home. When the two
audiences conflict, **coach-first wins** — design as a real production coach tool;
reviewers are served by its fidelity and rigor, and showcase moments appear only where
they don't cost usability.

## Product Purpose

A coach-facing dashboard that generates safe, highly personalized workouts and lets
the coach retrieve member context through an AI copilot. It replaces manual
context-piecing (workouts, injuries, goals, adherence, chats, biomarkers, labs) with
grounded retrieval, and replaces plan-from-memory with graph-driven generation.
Success: faster workout generation, injury-aware safety, and recommendations that can
be explained and audited.

## Positioning

Recommendations are driven by a knowledge graph, not the language model alone. Safety
is enforced **deterministically through graph traversal** — the walked path *is* the
provenance trace the coach sees. A neighboring LLM-wrapper product cannot truthfully
claim that every verdict carries the graph path that produced it, that the agent may
tighten but never loosen the safety floor, or that the trace is appended as work
happens rather than reconstructed afterward.

## Operating Context

- One coach, one member at a time (sample member: Jordan Rivera — recovering left-knee
  injury, no barbell at home, declining adherence, a workout to celebrate).
- Two Neo4j knowledge graphs: KG1 (Movement/Clinical — 50-exercise catalog, SNOMED
  anatomy snapshot, authored contraindications) and KG2 (Member Context — private per
  member). Vocabulary is canonical in `CONTEXT.md`; use its terms verbatim.
- Surfaces: a shared application header above a desktop split workspace. The Dashboard
  holds member context, the morning brief, and today's session; a persistent Copilot
  pane is the second first-class surface for workout generation and context Q&A. At
  narrow widths Copilot becomes an accessible drawer. Mock coach auth.
- All data is synthetic; no real member or personal data, ever.

## Capabilities and Constraints

- Workout generator: prompt + time window → structured plan (warm-up / main /
  cool-down with sets, reps, rest) plus a provenance trace; interactive adjustment via
  ConstraintSet deltas (exclusions, session injuries, equipment overrides).
- Safety: three-layer knowledge (clinical directives > contraindications > derived),
  verdicts exclude/caution/clear, deterministic safety floor the agent can only
  tighten. Stale observations are never silently used — any surface showing one must
  show its age.
- Copilot: typed retrieval tools over KG2 (never prose), every answer carries sources
  (tool + node ids), coach actions (message member, update brief task) execute only
  after an explicit coach confirm via action cards. Charts: server builds the series;
  the LLM never supplies data points.
- Stack (existing, not a choice to reopen): Next.js 16 / React 19 / Tailwind 4 /
  Base UI / Recharts frontend; FastAPI + LangGraph backend; Neo4j + Postgres;
  one-command dev (`pnpm dev`). AI responses target ~5s.
- Journey stage (new / building / recovering) is derived on load, never stored.

## Brand Commitments

- Product name: **Future Coach** — "Future" is the brand the product is built for;
  "Coach" names the coaching dashboard. This replaces the working title "Ridgeline"
  still present in the frontend (layout metadata, ridgeline-mark component); future
  work should migrate naming to Future Coach.
- Future's current identity is binding: **Season Mix** for editorial display and
  **Season Sans** for interface/body text, with ink, warm off-white, peach, lilac, and
  powder-blue roles sourced from Future's progress experience.
- The craft bar sits alongside Oura, Apple Fitness, and Hevy: premium fitness software,
  immediate scanability, restrained motion, and direct workout manipulation. Do not
  copy their layouts or brand assets.
- Voice is operational and brief. No policy narration, generic AI helper prose, or
  redundant explanations. Interface copy must help the coach decide or act.
- The selected shell has no dashboard sidebar. Global navigation is centered; member
  context is a thin shared strip; the Dashboard/Copilot split begins below it.

## Evidence on Hand

- `data/exercises.json` — the real 50-exercise catalog with packing scalars.
- `data/member-context.json` — one rich synthetic member engineered for the demo
  scenarios (left-knee injury, no barbell, declining adherence, celebration task).
- `docs/PRD.md` (assignment source), `docs/SPEC.md`, `docs/STANDARDS.md`,
  `docs/adr/0001–0005`, `CONTEXT.md` (canonical vocabulary).
- No real testimonials, customers, benchmarks, or pricing exist — never fabricate any.

## Product Principles

1. **The graph decides; the model narrates.** Safety and selection come from
   traversal; the LLM works at the edges and never invents data points or verdicts.
2. **Every claim carries its path.** Provenance traces, sources on answers, evidenced
   barriers — nothing asserted bare.
3. **The coach confirms every write.** AI proposes via action cards; nothing reaches
   the member or the record without an explicit confirm.
4. **Coach-first fidelity over demo spectacle.** Scanability, the morning ritual, and
   auditability outrank memorable flourish.
5. **Honest data age.** Stale values are shown with their age or not at all.

## Accessibility & Inclusion

Basics only (confirmed): semantic HTML and keyboard operability throughout; no formal
WCAG 2.2 AA compliance program for this take-home.
