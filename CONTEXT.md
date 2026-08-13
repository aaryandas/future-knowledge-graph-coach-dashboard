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

## Traversals

- **Safety trace** — the recorded path a safety decision walked: MemberInjury → exactMatch
  → ClinicalFinding → findingSite → AnatomicalStructure → isA* → AnatomicalStructure ←
  exactMatch ← Joint ← loads ← Exercise. The trace shown to the coach is the path actually
  walked, never a reconstruction.
