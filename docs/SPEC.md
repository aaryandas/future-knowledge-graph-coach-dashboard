# SPEC — Future Knowledge Graph Coach Dashboard

> Assembled from the wayfinder map (GNT-213) and its sixteen closed decisions.
> Vocabulary: `CONTEXT.md` (canonical — use its terms verbatim). Architecture
> decisions: `docs/adr/0002`–`0005`. Standards: `docs/STANDARDS.md`. The PRD is
> `docs/PRD.md`. This spec adds no new decisions; it indexes the made ones so a
> build plan can slice it without inventing anything.

## Problem Statement

A coach must piece together a member's context by hand before they can give
good advice: workouts, injuries, goals, adherence, chat history, biomarkers,
labs. This is slow, and it does not scale. A plan built this way can miss an
injury constraint. And when someone asks "why this exercise?", the coach has
no audit trail — the reasoning lived in their head.

## Solution

One coach-facing dashboard for one member at a time. A single chat surface
(the hideable copilot sidebar) drives both jobs: generate a safe, personalized
workout, and answer questions over the member's context. Two knowledge graphs
in Neo4j drive every recommendation: KG1 (Movement/Clinical, ontology-grounded)
and KG2 (Member Context). Safety verdicts come from deterministic graph
traversal — the walked path is the provenance trace the coach sees. The
dashboard main area shows the member at a glance (identity strip, stat tiles,
morning brief, today's session, Why-this-plan card), renders exact-scaled
charts, and gates every AI-proposed write behind a coach confirm click.

## User Stories

1. As a coach, I want to log in (mock auth) and land on my member's view, so that I start the day with context.
2. As a coach, I want an identity strip with tier, age, tenure, injury flag, and goals, so that I recall who the member is at a glance.
3. As a coach, I want four stat tiles — adherence, sleep, sessions, churn risk — each with a trend marker, so that I read the member's week in seconds.
4. As a coach, I want a morning-brief bar with my CoachTasks, so that I work my brief without digging.
5. As a coach, I want a journey-stage chip (new | building | recovering) with click-through evidence, so that I coach to where the member is on their journey.
6. As a coach, I want to request a workout with a prompt and a time window in chat, so that I generate a session without a form.
7. As a coach, I want a structured plan — warm-up, main, cool-down, with sets, reps, and rest — so that the member can follow it.
8. As a coach, I want the plan to fit the time window I gave, so that the session is realistic.
9. As a coach, I want every plan row to carry a verdict icon and any caution note, so that I see the safety state of each exercise.
10. As a coach, I want to edit a row's dose or swap an exercise from the session card, so that I tune the plan without retyping the request.
11. As a coach, I want "exclude deadlifts" to remove every deadlift variation, so that my exclusions hold.
12. As a coach, I want "her left knee is bothering her" to exclude or down-rank exercises that stress the knee through the anatomy hierarchy, so that sub-structures count too.
13. As a coach, I want "she has no barbell, only dumbbells and a kettlebell" to drop barbell-only exercises and surface equivalent alternatives, so that home sessions stay possible.
14. As a coach, I want a session injury to stay session-scoped until I confirm it, so that a chat remark never silently changes the member record.
15. As a coach, I want an adjusted plan to change only where the new constraint bites, so that the rest of the session stays familiar.
16. As a coach, I want a Why-this-plan card in plain sentences — removed, replaced, capped, unrecognized — so that I can explain every choice.
17. As a coach, I want an unrecognized term to appear as a visible chip with did-you-mean candidates I can click, so that nothing I said drops silently.
18. As a coach, I want an unmapped safety term flagged loudly as "not enforced", so that I never assume protection that is absent.
19. As a coach, I want short coaching notes to stream in after the plan renders, so that I get context without waiting for it.
20. As a coach, I want to ask the copilot member-specific questions and follow-ups, so that I get answers grounded in the member's actual data.
21. As a coach, I want every copilot answer to carry source chips, so that I can audit what was read.
22. As a coach, I want a quick-prompt palette, so that my common questions are one click.
23. As a coach, I want the four chart kinds — adherence trend, sleep week, message pattern, four-week comparison — exactly scaled with visible axis values, so that I read real numbers, not vibes.
24. As a coach, I want the churn-risk answer to show its Barriers with evidence chips, so that risk claims are auditable.
25. As a coach, I want stale values to state their age wherever they appear, so that I never act on outdated data unknowingly.
26. As a coach, I want to draft a member message from a brief task, edit the draft, and send it only on my confirm, so that the AI never messages a member on its own.
27. As a coach, I want to update a brief task through a confirmed action card, so that my brief stays current.
28. As a coach, I want my chat history — including re-rendered charts — preserved across sessions, so that I can revisit past answers.
29. As a coach, I want a graph view with lane-ruled paths and clickable node previews, so that I can inspect the graph behind a decision.
30. As a coach, I want a plan and its trace in about 2.5 seconds and answers inside ~5 seconds, so that the tool keeps my pace.
31. As a reviewer, I want one command path to run the whole system, so that evaluation is friction-free.
32. As a reviewer, I want a README with an architecture diagram, defended decisions, and three worked examples with traces, so that I can audit the reasoning.
33. As a reviewer, I want the safety decision computed by graph traversal with the walked path shown, so that safety is provable, not asserted.
34. As a reviewer, I want the ontology grounding (SNOMED, SKOS, PROV-O, COPPER, OPE-cited) doing real work in the graph, so that this is not semantic search with extra steps.

## Implementation Decisions

**Stack** (GNT-215). FastAPI + LangGraph backend on Python (uv, pytest, ruff).
Next.js frontend, TypeScript strict, Tailwind. Monorepo `backend/` +
`frontend/`; root `pnpm dev` / `pnpm lint` / `pnpm test` are the gate names.
LLM access through OpenRouter via LangChain interfaces: DeepSeek v4 flash for
chat, Qwen3 for embeddings, concept embeddings precomputed at build time.
Deploy: Railway, two services, Next.js rewrite proxy (no CORS). The skeleton,
CI, and Railway deploy are already live (GNT-221, GNT-227).

**Stores** (ADR-0005). Neo4j holds both knowledge graphs and is the system of
record for KG2. Traversals run in the store as parameterized Cypher; the
returned path is the provenance trace; Python applies the verdict matrix.
Postgres holds LangGraph threads and checkpoints, shared by both surfaces.
Locally docker compose boots both; CI uses service containers. The JSON files
under `data/` are seed data, not the store.

**Ingestion** (ADR-0005). Two stages. Acquire (build-time, rare) writes
versioned snapshot artifacts — the ontology subset of GNT-214 (~350 SNOMED
concepts via NCI EVS, ~8 COPPER barrier classes + ActionPlan, SKOS mappings in
one flat file, PROV-O starting-point terms as plain JSON). Ingest (every
environment) MERGEs all sources idempotently, keyed on stable IDs, stamping
`source`, `version`, `ingested_at` on every node. It runs as `pnpm seed`
locally, pre-deploy, and in CI before tests. A second member is one more seed
document.

**Graph schema** (GNT-216, CONTEXT.md). Node and edge types keep the glossary
spelling verbatim as labels and relationship types. SNOMED snapshot concepts
are first-class nodes, so a safety trace shows real clinical nodes. The PRD's
`part-of` cover is realized as an upward `isA` walk. KG2 bridging into KG1 at
ingest uses the resolver's exact pass only; an unresolved mention keeps its
raw string and creates no edge.

**Concept resolver** (GNT-218). One parametrized `resolve(text, vocab)`
returning a Resolution value — concept, confidence, pass, ranked candidates,
raw text, first-class modifiers. Failure is a Resolution, never an exception.
Passes in fixed order: exact (NFKC normalization, token aliases, SNOMED
synonyms) → fuzzy (rapidfuzz token_set_ratio, accept ≥ 85) → vector
(precomputed embeddings, numpy cosine, accept ≥ 0.65, a calibration knob;
skipped cleanly offline). Below-floor policy per caller: generator terms get a
visible omission chip with did-you-mean candidates; safety terms warn loudly
and are never guessed; ingest is exact-only.

**Safety model** (ADR-0002). Verdicts exclude | caution | clear from a
traversal over three layers, highest precedence first: member clinical
directives (resolver-parsed), the authored condition file (four conditions;
a citation is mandatory per row; ingestion rejects uncited rows), and the
SNOMED anatomical fallback (findingSite → isA* → Joint → loads, caution).
Status and severity escalate only. The agent may tighten the floor, never
loosen it; agent tightenings are recorded as agent decisions. Every verdict
carries the walked graph path.

**Generation runtime** (ADR-0003, GNT-219). A deterministic LangGraph
StateGraph. The LLM sits at two edges only: interpretation (one
structured-output call → an Intent of raw mention strings, never concept ids;
temperature 0, one retry, then visible failure) and annotation (optional,
streams after the plan, tighten-only). Everything between is deterministic:
resolve → verdicts → ranking → packing. Adjustments go through the same
interpretation edge as deltas, merge into a checkpointed ConstraintSet, and
the pipeline fully re-runs; plans are never patched in place. A session injury
feeds the same traversal but stays session-scoped, with a visible suggestion
to persist. Alternatives emerge from re-ranking; the trace pairs each dropped
exercise with its packed replacement as a Substitution (shared pattern first,
then muscle overlap). TraceEvents append to graph state as the work happens;
pure functions return their events. Parts per turn: `data-plan`, `data-trace`,
`data-constraints`, then streamed text.

**Packing** (GNT-224). Fixed skeleton warm-up/main/cool-down at 15/70/15 with
a pattern→section eligibility table; the Intent's focus filters main only.
Scored greedy selection (goal match + coverage gain + priority tier − caution
− dislike), ties break on name then id — same inputs, byte-identical plan.
A one-side exercise packs as one per-side entry counting both sides; no
right-side exercise is ever invented. Fixed cut order for short windows:
cool-down → warm-up → main sets → lowest-ranked main entries, always one
entry per section. Every fixed number lives in one constants file. The
packer's output type is the `data-plan` payload.

**Copilot** (ADR-0004, GNT-220). A LangGraph tool-loop agent over KG2, five
tool rounds max, one thread per member. Seven typed read tools, each one
documented Cypher traversal returning typed JSON plus node ids read:
observations, sessions, chat messages, goals, injuries, brief, profile.
Charts through one `render_chart` tool with a closed set of four kinds; the
server builds the series; the LLM picks kind and window only. Rendered
numbers come from tool data parts, never from prose. Every answer carries a
`data-sources` part. Quick prompts are canned messages through the same loop.
Writes (send member message, update task) pause on a LangGraph interrupt; the
action card offers Send / Edit / Discard; only a coach click executes, as one
Cypher transaction stamped with actor and timestamp. Parts: `data-chart`,
`data-sources`, `data-brief`, `data-action`, text.

**Journey and longitudinal weighting** (GNT-228). Journey stage is a derived
read (new | building | recovering; precedence recovering > new > building)
computed on every KG2 load from injury status, tenure, and history — never
stored, never an LLM judgment, always evidence-carrying. Churn risk stays a
separate dimension (brief level + evidenced Barriers built at ingest). One
constants table gives per-Observation-kind relevance windows (sleep-night 7 d;
adherence-week 4 w; resting-hr and hrv 30 d; weight 90 d; labs latest-value,
stale past 180 d). A stale value always shows its age. The reads act through
the two existing LLM edges (tighten-only), one stage identity chip,
window-scoped copilot tools, and two labeled tone facts in the copilot
context.

**Dashboard UI** (GNT-226; prototype `docs/prototypes/dashboard.html`). One
chat surface — the hideable copilot sidebar; a plan request answers "Session
ready" and renders on the dashboard. Main area top-to-bottom: identity strip,
four stat tiles with trend markers, slim brief bar, Today's session card
(two-line rows, verdict icon, ✎ edit dose, ⇄ swap), Why-this-plan card
(plain sentences with colored markers, no tool names). Mock login in front;
Member and Graph view behind pill tabs. Graph view: lane-ruled, zero edge
crossings, value-labeled pills, minimal edge tags, clickable glass previews
with an "Ask copilot" hand-off. Visual language: Oura-referenced dark neutral,
liquid-glass materials, color only for data and status, zero explainer text,
reduced-motion and reduced-transparency fallbacks. UI kit: base-ui + recharts
+ Sonner on one Tailwind token theme (STANDARDS.md); any other UI dependency
needs an ADR.

**Contracts.** `useChat` drives both surfaces; the useChat thread id is the
LangGraph thread id. Pydantic models are the source of truth for every
`data-*` part; the frontend mirrors them in one typed parts file, the only
frontend↔API contract.

**Observability** (GNT-225). LangGraph's built-in LangSmith export, zero
tracing code, on only when the two env vars are set. The coach-facing trace
never depends on it.

**README and evidence** (GNT-230). README sections mirror the PRD's seven
deliverable bullets in order, plus an ontology table. Three demo scenarios on
Jordan Rivera: injury case, limited-equipment case, mid-chat adjustment.
Evidence collects during the build into `docs/evidence/` — per scenario a plan
JSON, a trace JSON, one screenshot; plus the build plan and gate outcomes.
Filling `docs/evidence/` is a build requirement, so the README is assembled,
not excavated.

## Testing Decisions

A good test exercises external behavior at a module's documented interface and
names that behavior in glossary terms. A test that reaches past an interface
is rejected; fix the module shape instead. Vary behavior by passing a
different adapter (fake LLM, fixture embeddings), never by patching internals.

Tests are required at exactly three seams (GNT-229) — the PRD floor:

- **Resolver seam** — `resolve(text, vocab) -> Resolution`. Table-driven
  pytest from one committed cases file: exact and alias hits, modifier
  extraction, fuzzy typos, vector semantic hits, below-floor garbage pinning
  both thresholds, and the real member strings. Exact cases assert the pass;
  vector cases read committed embedding fixtures.
- **Safety seam** — the verdict function, against a Neo4j service container
  seeded by the real ingest script (seeding doubles as the ingest check).
  Covers the three layers, the escalation matrix, and the walked-path
  property.
- **CI smoke** — ingest runs green and `/api/health` responds.

CI is hermetic: no external network, no keys; local service containers are
allowed. Everything else is untested by decision — no packer suite, no
stream-protocol tests, no frontend tests beyond the compiler. Prior art: the
repo is a scaffold with the gate proven red on a broken test; the conventions
above come from `docs/STANDARDS.md`.

## Out of Scope

- Real authentication or multi-tenant member management — mock auth, one
  member shipped. A second member is a seed document, not a feature.
- Any real member or personal data. Everything stays synthetic.
- A built evaluation pipeline. The production-evaluation deliverable is a
  README prose section.
- Tests beyond the three seams above.
- Multi-day program generation. Splits are per-request coaching, never stored.
- Event log / replayable audit store. Revisit only if it becomes a
  requirement.
- Runtime LLM generation of contraindication knowledge. New conditions go
  through the cited, human-approved authored file.
- A graph-rendering library. The graph view ships hand-drawn SVG; react-flow
  would need an ADR.

## Further Notes

- Submission constraint (not in the PRD): implementation must use Python and
  LangGraph. The stack decision already honors it.
- All human-facing prose — README, ADRs, UI copy, this spec — follows
  ASD-STE100 Simplified Technical English. UI copy carries zero explainer
  text.
- `OPENROUTER_API_KEY` is not yet set on Railway. Set it when the first LLM
  feature deploys.
- The multi-agent build workflow is itself PRD-graded material; keep
  collecting evidence for the "how AI built this" README section as the build
  runs.
- Latency budget: plan + trace at ~2.5 s, answers inside ~5 s, annotation
  streams late and is never load-bearing.
