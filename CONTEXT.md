# Ubiquitous Language

Glossary for the KG coach dashboard. Terms here are canonical — issues, code, tests, and
docs use these words and no synonyms.

## The two graphs

- **Movement/Clinical Graph (KG1)** — the shared, read-only reference graph: the exercise
  catalog, its taxonomy, the SNOMED snapshot, and authored safety knowledge. Identical for
  every member.
- **Member Context Graph (KG2)** — one member's world: profile, goals, preferences,
  injuries, equipment, history, observations, conversation. Private per member; every
  product traversal starts here and may bridge into KG1.

## KG1 node types

- **Exercise** — one of the 50 catalog entries; carries its packing scalars (rep duration,
  priority tier, bilateral pairing) as properties.
- **MuscleGroup** — a muscle group an Exercise targets (19).
- **Joint** — a joint or spine region an Exercise loads (9).
- **MovementPattern** — a named pattern an Exercise performs (36).
- **Equipment** — an equipment type an Exercise requires (32).
- **Injury** — an *authored contraindication anchor* (e.g. patellofemoral pain syndrome):
  the domain-side handle that safety edges hang off. Not a member's injury — see
  MemberInjury.
- **AnatomicalStructure** — a SNOMED anatomy concept from the build-time snapshot; carries
  its SNOMED code, preferred term, and synonyms.
- **ClinicalFinding** — a SNOMED disorder/finding concept from the snapshot; same
  properties.

## KG1 edge types

- **targets** — Exercise → MuscleGroup.
- **loads** — Exercise → Joint.
- **performs** — Exercise → MovementPattern.
- **requires** — Exercise → Equipment.
- **findingSite** — ClinicalFinding → AnatomicalStructure (SNOMED `has_finding_site`).
- **isA** — AnatomicalStructure → AnatomicalStructure (SNOMED hierarchy; "part-of" cover is
  realized as an upward isA walk).
- **exactMatch** — a domain node (Joint, Injury) → its SNOMED concept node. Carries the
  SKOS predicate as a property so weaker matches (broadMatch) reuse the edge type.
- **contraindicates** — Injury → MovementPattern | Joint. The safety edge. Its grain and
  exclude-vs-caution semantics are owned by the safety-model decision (GNT-217).

## KG2 node types

- **Member** — the person being coached; profile scalars live here as properties.
- **Goal** — a member's stated objective, with priority and target date.
- **MemberInjury** — a member's actual injury instance (status, severity, side, since).
  Distinct from KG1's Injury anchor; bridges to its ClinicalFinding via exactMatch.
- **WorkoutSession** — one planned or completed workout in the member's history.
- **Observation** — one typed, timestamped measurement (kind: adherence-week, sleep-night,
  weight, resting-hr, hrv, blood-panel, dexa, …). New health dimensions are new kinds, not
  new node types.
- **ChatMessage** — one message in the member–coach conversation, with sender and
  timestamp.
- **Barrier** — a COPPER-derived obstacle to adherence (time constraint, pain, motivation
  dip, …) identified for this member; must be evidenced, never asserted bare.
- **CoachTask** — an actionable item on the coach's morning brief (celebrate, check-in),
  after COPPER's ActionPlan pattern.
- **Journey stage** — a derived read of where the member is on their journey: **new**,
  **building**, or **recovering**. Computed on load from tenure, history, and injury
  status; never stored, never authored. Orthogonal to churn risk, which is its own
  dimension (Barrier, CoachTask).
- **Relevance window** — the per-Observation-kind period in which a value counts as
  current (nightly kinds have short windows; lab kinds have none and are always the
  latest value).
- **Stale** — outside the relevance window. A stale value is never silently used: any
  surface that shows or reasons over it must show its age.

## KG2 edge types

- **pursues** — Member → Goal.
- **has** — Member → MemberInjury.
- **owns** — Member → Equipment (KG1 bridge).
- **performed** — Member → WorkoutSession.
- **observed** — Member → Observation.
- **said / received** — Member → ChatMessage (direction = sender).
- **dislikes** — Member → Exercise (KG1 bridge), when the stated dislike resolves; raw
  string retained otherwise.
- **included** — WorkoutSession → Exercise (KG1 bridge), when the history name resolves.
- **evidencedBy** — Barrier → Observation | ChatMessage | WorkoutSession. The edge that
  makes churn reasoning auditable.
- **addresses** — CoachTask → Barrier | Goal | WorkoutSession.

## Safety vocabulary

- **Contraindication** — general clinical knowledge that a condition makes a movement
  inadvisable ("PFPS contraindicates loaded deep knee flexion"). Textbook content, true
  for every member; lives in KG1. Never member-specific — see Clinical directive.
- **Clinical directive** — a member-specific restriction or clearance written by a
  clinician into that member's injury record ("cleared for low-impact loading; avoid
  plyometrics"). The highest-precedence safety knowledge; lives in KG2.
- **Verdict** — the safety filter's per-exercise outcome: **exclude** (never enters a
  plan), **caution** (selectable, down-ranked, must carry a modification note), or
  **clear**. Every verdict carries the graph path that produced it.
- **Safety floor** — the deterministic exclusion set produced by graph traversal. The
  agent may tighten the floor (add caution or exclusions from softer context), never
  loosen it; agent tightenings are recorded as agent decisions, distinct from graph
  decisions.
- **Escalation rule** — injury status and severity only ever escalate a verdict, never
  soften authored knowledge; a resolved injury stops filtering but stays visible in
  provenance.

## Resolver vocabulary

- **Resolution** — the outcome of resolving one free-text mention against one vocabulary:
  the matched concept (or none), a confidence, the pass that produced it, ranked
  runner-up candidates, the raw text, and any modifiers. Failure is a Resolution too,
  never an exception.
- **Pass** — one of the resolver's three attempts, in fixed order: exact (normalization,
  aliases, SNOMED synonyms), fuzzy (typo/word-order tolerance), vector (semantic
  similarity). A Resolution names the pass that matched; below every pass's floor the
  pass is "none".
- **Modifier** — a free-text qualifier extracted from a concept mention ("box-supported"
  in "Goblet Squat (box-supported)"), carried structurally on the Resolution and the
  edge its caller creates. An open set: never resolved against KG1, which defines no
  modifier concepts.

## Generation vocabulary

- **Intent** — the structured interpretation of one coach message in a generation session:
  a focus (closed set) plus raw mention strings for targets, exclusions, injuries, and
  equipment. Mentions are never concept ids — grounding a mention is exclusively the
  resolver's job.
- **ConstraintSet** — the accumulated, resolved constraints of one generation session:
  exclusions, session injuries, and the equipment override. Each adjustment merges a delta
  into the set; a plan is always generated from the full set, never patched in place.
- **Session injury** — an injury reported mid-conversation ("her left knee is bothering
  her"). Feeds the same safety traversal as a recorded MemberInjury but stays scoped to the
  session; it reaches the member's record only by explicit coach confirmation.
- **TraceEvent** — one recorded reasoning step in a plan's provenance trace (kinds:
  resolution, verdict, substitution, packing, agent), attributed to graph or agent. The
  trace is the ordered list of TraceEvents, appended as the work happens — never
  reconstructed afterward.
- **Substitution** — the recorded pairing of a dropped exercise with its packed
  replacement, judged by graph structure: shared movement pattern first, then muscle
  overlap. A trace artifact, not a second selection path — the replacement is whatever the
  ranking actually picked.

## Packing vocabulary

- **Section** — one of the three parts of a plan: warm-up, main, cool-down. A fixed
  pattern→section table decides which exercises can enter each section. The Intent's focus
  filters the main section only.
- **Plan entry** — one line of a plan: exercise id and name, sets, reps or hold time,
  rest, per-side flag, weight flag, verdict, and minutes. A one-side exercise packs as one
  per-side entry that counts both sides; the app never invents the missing right-side
  exercise.
- **Cut order** — the fixed order the packer shrinks a plan that does not fit: cool-down,
  warm-up, main sets, lowest-ranked main entries. A plan always keeps one entry per
  section.
- **Packing constants** — every fixed packing number (section time split, default sets and
  reps, rest times) lives in one constants file.

## Copilot vocabulary

- **Retrieval tool** — one typed read function over KG2 that the copilot agent can call.
  Each retrieval tool is one documented graph traversal. It returns typed data plus the
  node ids it read. It never returns prose.
- **Coach action** — a write the copilot can propose: send the member a message, or
  update a brief task. A coach action executes only after the coach confirms it.
- **Action card** — the rendered proposal for one coach action. It shows the exact
  change. The coach confirms or discards it.
- **Source** — one record of what an answer read: the tool called and the node ids it
  returned. Every copilot answer carries its sources.
- **Chart kind** — one member of the closed set of charts the copilot can draw
  (adherence trend, sleep week, message pattern, four-week comparison). The server
  builds the series; the LLM never supplies data points.

## Traversals

- **Safety trace** — the recorded path a safety decision walked: MemberInjury → exactMatch
  → ClinicalFinding → findingSite → AnatomicalStructure → isA* → AnatomicalStructure ←
  exactMatch ← Joint ← loads ← Exercise. The trace shown to the coach is the path actually
  walked, never a reconstruction.
