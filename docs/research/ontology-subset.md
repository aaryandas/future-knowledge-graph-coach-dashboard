# Ontology subset for the Movement/Clinical KG (GNT-214)

Research findings for grounding the domain graph without wholesale ingestion. Every SNOMED
claim below was verified live against the NCI EVS REST API on 2026-08-10 (SNOMED CT US
edition `2025_09_01`); OPE/COPPER claims come from primary sources (archived BioPortal
metadata, the COPPER paper, and the COPPER OWL file itself).

**Recommendation in one paragraph.** Ground anatomy and the injury model in SNOMED CT via
EVS (13 verified concepts + descendant closures, snapshotted at build time). Adopt OPE's
five-facet exercise description as the *schema frame* but do not import its classes — the
ontology is alpha, unmaintained since 2013, and none of its 634 classes has a definition.
Pull COPPER's barrier / coping-plan vocabulary for the *member-context* graph (adherence and
churn reasoning), not the movement graph — its activity taxonomy stops at "Resistance
Training" and it contains no anatomy, injuries, or concrete equipment. Serialize catalog →
ontology alignments as a flat JSON mapping file with SKOS predicates (exactMatch only where
verified 1:1; unmapped-with-note beats a forced match), and shape the per-exercise
provenance trace with the minimal PROV-O core (Entity / Activity / Agent + used /
wasGeneratedBy / wasDerivedFrom / wasAssociatedWith), skipping the qualified-relation
pattern entirely.

---

## 1 · SNOMED CT via NCI EVS — the anatomical & clinical backbone (PULL)

### Verified concept table

All codes fetched from `https://api-evsrest.nci.nih.gov/api/v1/concept/snomedct_us/{code}`
(no auth). Browser links: `https://evsexplore.semantics.cancer.gov/evsexplore/concept/snomedct_us/{code}`.

| Catalog term (`joints_loaded`) | SNOMED code | Preferred term | SKOS predicate |
|---|---|---|---|
| shoulder | `31398001` | Joint structure of shoulder region | exactMatch |
| elbow | `16953009` | Elbow joint structure | exactMatch |
| wrist | `74670003` | Wrist joint structure | exactMatch |
| hip | `24136001` | Hip joint structure | exactMatch |
| knee | `49076000` | Knee joint structure | exactMatch |
| ankle | `70258002` | Ankle joint structure | exactMatch |
| cervical spine | `786964009` | Structure of cervical spine joint region | exactMatch |
| thoracic spine | `786965005` | Structure of thoracic spine joint region | exactMatch |
| lumbar spine | `786966006` | Structure of lumbar spine joint region | exactMatch |

Notes on two deliberate choices:

- **shoulder → `31398001`** (joint structure of shoulder *region*), not `85537004`
  Glenohumeral joint structure. The catalog's "shoulder" means the shoulder complex; the
  region concept subsumes glenohumeral, acromioclavicular, etc., so injury cover is wider
  and correct.
- **Spines → the 2018-era "Structure of X spine joint region" concepts**, which subsume the
  facet-joint structures (`427091002` cervical, `428132006` thoracic, `428001008` lumbar)
  that actual spine complaints attach to.

### Injury concepts (member scenario)

| Concept | SNOMED code | Notes |
|---|---|---|
| Patellofemoral pain syndrome | `430725003` | Preferred term is *Patellofemoral stress syndrome*; "Patellofemoral pain syndrome" and "Patellofemoral syndrome" are registered SNOMED synonyms — resolver must index synonyms, not just preferred terms |
| PFPS of **left** knee joint | `49631000087103` | Pre-coordinated laterality; exact match for Jordan Rivera's `inj_knee_left`; is-a child of `430725003` |
| PFPS of right knee joint | `49641000087109` | Kept for symmetry of the laterality pair |
| Structure of patellofemoral joint | `129160003` | The **finding site** of `430725003` (verified `has_finding_site` association) |
| Knee region structure | `72696002` | Optional wider traversal root: also subsumes Bone structure of patella `64234005`, patellar ligament `18033002`, soft tissue of knee region |

### How the "part-of" hierarchy actually works (verified)

EVS exposes SNOMED as a **pure is-a DAG** (`RELA: isa` / `inverse_isa`); there is no
separate part-of relation to ingest. SNOMED anatomy achieves part-cover through its
SEP-style "structure of X" concepts: *Knee joint structure* subsumes its parts via is-a. So
the PRD's `part-of` edge is implemented as **descendant closure of the joint's structure
concept** — verified:

- `GET /concept/snomedct_us/49076000/descendants?maxLevel=5&pageSize=500` → 197 concepts,
  **including** `129160003` Structure of patellofemoral joint (via `244548003` Component of
  knee joint), patellar retinacula, articular cartilage of patella, knee ligaments.
- `GET /concept/snomedct_us/72696002/descendants?maxLevel=3` → 136 concepts, adding bone
  structure of patella and knee-region soft tissue.

So: member has PFPS → finding site `129160003` → that code is inside the descendant
closure of catalog joint "knee" → every exercise with `joints_loaded: knee` is flagged, and
the flag is justified by a concrete graph path (`430725003 → has_finding_site → 129160003 →
isa* → 49076000 → skos:exactMatch → fkg:joint/knee`). That path *is* the provenance trace
for the safety filter.

Disorders attach to anatomy via `has_finding_site` associations; the inverse
(`/inverseAssociations` on a structure) lists disorders and procedures sited there — useful
offline for building a contraindication seed list, too noisy for runtime.

### Verified query patterns + observed latency

Base: `https://api-evsrest.nci.nih.gov/api/v1` — no API key, plain HTTPS GET.

| Pattern | Example | Observed latency |
|---|---|---|
| Term search | `/concept/search?terminology=snomedct_us&term=patellofemoral%20pain%20syndrome&pageSize=4` | 0.28–0.35 s |
| Concept + selected fields | `/concept/snomedct_us/430725003?include=summary,synonyms,parents` | ~0.22 s |
| Full concept (roles/associations) | `/concept/snomedct_us/430725003?include=full` | ~0.25 s |
| Children | `/concept/snomedct_us/72696002/children` | ~0.23 s |
| Descendant closure | `/concept/snomedct_us/49076000/descendants?maxLevel=5&pageSize=500` | ~0.35 s |
| Paths to root | `/concept/snomedct_us/129160003/pathsToRoot` | ~1.1 s (37 paths — multi-parent DAG; avoid at runtime) |

Latencies measured from a US-west residential connection, single requests, no retries
needed. Search `type=contains` is the default; `total` counts are terminology-wide noise —
read only the top hits.

**Snapshot, don't query live.** The API is fast enough for live use, but it has no SLA, and
the app has a ~5 s AI budget. Recommended: a build-time script fetches the 13 concepts +
their synonym lists + the 9 descendant closures and commits the result as a JSON data file
(~350 concepts total). Live EVS access remains a refresh job and a resolver fallback for
unrecognized clinical terms, degrading gracefully to "unmapped" on timeout.

### PULL / LEAVE OUT

**Pull:** the 13 concepts above; descendant closures of the 9 joint concepts; synonym lists
(feeds the resolver's exact and fuzzy passes); `has_finding_site` for injury → anatomy.

**Leave out — and why:**
- **The rest of the terminology** (~350k concepts): only anatomy cover and injury siting do
  graph work here; everything else is dead weight that slows traversal and review.
- **Procedures, morphology, clinical-findings tree wholesale:** we recommend exercises, we
  don't diagnose; a workout planner holding "Arthroplasty of patella" invites misuse.
- **"Entire X" vs "Structure of X" distinction:** SEP's *Entire* concepts exist for precise
  clinical recording; exercise safety always wants the inclusive *Structure* semantics. We
  keep structure concepts only.
- **Pre-coordinated laterality beyond the PFPS pair:** laterality is a property on the
  member's injury node (`side: left`), not 2× the anatomy graph. SNOMED's lateralized
  concepts would double every closure for zero traversal gain.
- **Live dependence on EVS in the request path:** determinism and the latency budget; see
  snapshot note.

---

## 2 · OPE — adopt the frame, skip the classes (CITE, selective PULL)

### What actually exists (primary evidence)

The live BioPortal page blocks non-browser clients (403), so metadata was taken from the
Wayback snapshot of 2024-10-07 (URL in Sources):

- **Status: Alpha. Version 0.0.1, last uploaded 2013-03-21.** No submissions since.
- **634 classes, 27 properties, 0 individuals, max depth 9 — and "Classes with no
  definition: 634."** Not one class in the ontology has a textual definition.
- Author: Juan-Carlos Foust (Stanford contact address). **No accompanying publication
  exists**; the exergame-ontology paper (Bamparopoulos et al. 2016) cites OPE only as a
  BioPortal URL, and the PACO review (JMIR 2019) concludes OPE "has many limitations to be
  considered as an ontology to support representing nongame-based physical activities."
- BioPortal's own description of scope: an exercise described by **functional movements,
  engaged musculoskeletal system parts, related equipment or monitoring devices, intended
  health outcomes, and target ailments** (treatment/prevention).

### PULL

The **five-facet description frame** — it is almost exactly our edge set, which is the
grounding that matters:

| OPE facet | Our KG edge |
|---|---|
| functional movements | `Exercise → movement_pattern` |
| engaged musculoskeletal parts | `targets` (muscle) / `stresses` (joint) |
| related equipment | `requires` (equipment) |
| intended health outcomes | goal alignment (member goals) |
| target ailments | `contraindicated-for` / therapeutic-for (injury) |

We cite OPE in the schema doc as the published precedent for this shape, and optionally
record `skos:closeMatch` rows to individual OPE class URIs where a label matches a catalog
string exactly (best-effort, zero runtime dependence).

### LEAVE OUT — and why

- **All 634 class URIs as canonical identifiers.** A URI whose class has no definition
  carries no semantics beyond its label string — aligning to it is grounding theater. Add
  alpha status, 12+ years unmaintained, no publication to interpret intent, and
  distribution locked behind a bot-blocked UI / API-key REST, and OPE URIs become an
  operational liability with no compensating meaning.
- **OPE anatomy and injury branches specifically:** SNOMED covers the same ground with
  definitions, synonyms, maintenance, and a verified no-auth API. Never ground the same
  concept in two ontologies — one canonical home per concept (SNOMED for anatomy/injury),
  or traversals fork.

---

## 3 · COPPER — personalization vocabulary for the member-context graph (selective PULL)

### What actually exists (primary evidence)

Paper: *Development and evaluation of the COntextualised and Personalised Physical activity
and Exercise Recommendations (COPPER) Ontology*, IJBNPA 2025. OWL verified by downloading
`COPPER.owl` from the project GitHub (CC-BY 4.0, RDF/XML, builds on BCIO/ADDICTO imports):

- 288 classes, 9 data properties, 64 object properties (paper); upper-level action-plan /
  coping-plan model with lower ontologies: **Profile (22), Planning (14), Activity (67),
  Context (16), Barrier (90), Coping Strategy (96)**.
- Object properties seen in the OWL: `hasActionPlan`, `hasCopingPlan`, `hasBarrier`,
  `hasSolution`, `hasPlannedLocation`, `hasPlannedSocialContext`, `hasPlannedDuration`,
  `needsEquipment`, `needsExperience`, `hasIntensity`, `hasPrice`.
- Barrier classes directly relevant to our member data: *An injury*, *Pain from the
  activity*, *activity-induced pain*, *I will not be motivated*, *I won't have the time*,
  *I won't have the energy*, *feeling tired*, *goal conflict concerning time / energy*.
  Coping-strategy classes are BCT-tagged (behaviour change techniques), e.g. *advise goal
  integration BCT*, *Provide a positive consequence or reward*.
- **Granularity ceiling:** the Activity ontology is Compendium-style leisure/household
  activities — "Resistance Training" is a *single class*. Equipment is just
  `Equipment / SportsEquipment / ObjectsOfDailyLiving`. The paper is explicit that anatomy,
  pathology, and injury classification are out of scope. Logic ships as SWRL rules with
  binary relevant/not-relevant semantics.

### PULL (into KG2, the Member Context graph)

- Node types **Barrier** and **CopingStrategy**, typed to COPPER classes, plus the
  **ActionPlan/CopingPlan pattern** with `hasBarrier` / `hasSolution` edges.
- The ~8 barrier classes listed above as canonical churn/adherence vocabulary. Jordan's
  skipped session ("work blew up and I was wiped") becomes a barrier instance typed
  {time-conflict, low-energy}; her knee flare typed *activity-induced pain*. Churn
  reasoning then traverses member → barrier → matched coping strategies, and the copilot
  can ground "what should I suggest?" in BCT-tagged strategies instead of freeform LLM text.
- Planned-context slots (location / social context / duration) as properties on planned
  sessions — they line up with `preferences.preferred_days` / `preferred_session_minutes`.

### LEAVE OUT — and why

- **The Activity taxonomy and Equipment classes:** one "Resistance Training" class cannot
  represent a 50-exercise catalog; our catalog *is* the finer-grained ontology here.
  Mapping 50 exercises to one class would be `skos:broadMatch` noise with no traversal use.
- **SWRL rules and the decision-tree logic:** our safety reasoning is graph traversal in
  our own store; importing a rules engine's rule set we won't execute is dead weight.
- **BCIO/ADDICTO import closure and persona individuals (CP_Christa …):** triples the
  footprint, zero domain gain; the personas are the paper's test fixtures.
- **Profile classes:** they duplicate fields our member JSON already has with richer values.

---

## 4 · SKOS — mapping predicates and JSON serialization

Source: SKOS Reference (W3C REC), §10 mapping properties: `exactMatch`, `closeMatch`,
`broadMatch`, `narrowMatch`, `relatedMatch`; all are sub-properties of
`skos:mappingRelation`; `exactMatch` is transitive and chains across vocabularies, so a
wrong exactMatch poisons downstream inference — the spec reserves it for "a high degree of
confidence" of interchangeable use.

Policy per catalog dimension:

| Dimension | Predicate | Rationale |
|---|---|---|
| 9 joints → SNOMED | `skos:exactMatch` | Verified 1:1, interchangeable in queries (table above) |
| Injuries → SNOMED | `skos:exactMatch` | e.g. member injury type → `430725003` / `49631000087103` |
| 19 muscle groups → SNOMED muscle structures | `exactMatch` where 1:1 (e.g. quads, biceps); `broadMatch` for catalog groupings like "core", "upper back" that are broader-than/askew-to any single SNOMED structure | catalog terms are trainer groupings, not anatomical units |
| 32 equipment types → OPE labels | `skos:closeMatch` at most | OPE classes are undefined; label match is evidence of similarity, not identity |
| 36 movement patterns | mostly **unmapped, with a note** | no surveyed ontology owns "lower push - split squat"-level patterns; our catalog is the authority |

Rule of the file: **never force a mapping — an absent mapping with a recorded reason beats
a wrong exactMatch.**

**Serialization without a triple store:** one flat JSON file with a JSON-LD `@context`, so
it is simultaneously app-readable and valid SKOS RDF:

```json
{
  "@context": {
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "sct": "http://snomed.info/id/",
    "fkg": "https://example.com/fkg/"
  },
  "mappings": [
    {
      "source": "fkg:joint/knee",
      "predicate": "skos:exactMatch",
      "target": "sct:49076000",
      "targetLabel": "Knee joint structure",
      "confidence": 1.0,
      "verified": "2026-08-10, EVS snomedct_us 2025_09_01"
    },
    {
      "source": "fkg:pattern/lower push - split squat",
      "predicate": null,
      "note": "no ontology target; catalog is authoritative"
    }
  ]
}
```

`confidence`/`verified`/`note` are deliberately outside SKOS semantics (SKOS has no
confidence property). If the project later wants a standards-blessed exchange format for
exactly this shape, **SSSOM** (Simple Standard for Sharing Ontology Mappings) defines
subject/predicate/object + confidence + justification per row — the JSON above converts to
SSSOM TSV mechanically. Not needed now; noted as the upgrade path.

---

## 5 · PROV-O — minimal subset for the per-exercise trace

Source: PROV-O (W3C REC). The **Starting Point terms** are sufficient:

- **Classes:** `prov:Entity`, `prov:Activity`, `prov:Agent` (+ `prov:SoftwareAgent`).
- **Properties:** `prov:used`, `prov:wasGeneratedBy`, `prov:wasAssociatedWith`,
  `prov:wasDerivedFrom`, `prov:startedAtTime` / `prov:endedAtTime`.

Trace shape: one generation run is an `Activity`; the plan and each selection/exclusion are
`Entities` generated by it; the activity `used` the member-context entities and the graph
paths that justified each decision; agents are the runtime (SoftwareAgent) and the coach.
Plain-JSON serialization with PROV terms as keys:

```json
{
  "activity": {
    "id": "gen_2026-08-10T09:14",
    "prov:startedAtTime": "2026-08-10T09:14:02Z",
    "prov:wasAssociatedWith": ["agent:runtime@1.0", "agent:coach_01HXSAM"],
    "prov:used": ["member:mbr_01HX9JORDAN/injuries/inj_knee_left",
                   "member:mbr_01HX9JORDAN/equipment_available"]
  },
  "selections": [{
    "exercise": "fkg:exercise/hip-thrust",
    "prov:wasGeneratedBy": "gen_2026-08-10T09:14",
    "prov:wasDerivedFrom": ["fkg:exercise/hip-thrust", "goal:goal_strength"],
    "reason": "targets glutes; knee not in joints_loaded"
  }],
  "exclusions": [{
    "exercise": "fkg:exercise/jump-squat",
    "prov:wasGeneratedBy": "gen_2026-08-10T09:14",
    "prov:wasDerivedFrom": ["member:.../inj_knee_left", "sct:430725003"],
    "graphPath": ["sct:430725003", "has_finding_site", "sct:129160003",
                   "isa*", "sct:49076000", "skos:exactMatch", "fkg:joint/knee",
                   "stresses⁻¹", "fkg:exercise/jump-squat"],
    "reason": "PFPS finding site is within knee joint descendant closure"
  }]
}
```

**Leave out — and why:**
- **Qualified relations** (`qualifiedUsage`, `qualifiedGeneration`, `Influence` classes):
  they exist so RDF can attach attributes to a relation; plain JSON attaches attributes
  inline for free. Adopting them doubles trace size for no reader benefit.
- **Bundles:** for exchanging provenance *between* systems; we have one system.
- **Collections, Delegation (`actedOnBehalfOf`), Invalidation, `alternateOf` /
  `specializationOf`, `prov:Plan`:** no corresponding question in the product ("who
  delegated to whom?" is not a coach question). Each is re-addable later without breaking
  the JSON shape.

---

## 6 · Fallback plan

The design already assumes the safe fallback: a **hand-rolled `fkg:` mini-ontology** (node
types Exercise, MuscleGroup, Joint, MovementPattern, Equipment, Injury; edges `targets`,
`stresses`, `requires`, `part-of`, `contraindicated-for`) is the runtime graph either way —
external ontologies only *annotate* it. Failure modes:

- **EVS unreachable at snapshot time:** the verified code table in this document is the
  seed — SNOMED codes are stable identifiers; commit them and re-fetch closures when the
  API returns. Resolver degrades from "SNOMED-grounded" to "catalog-string" matching with a
  logged provenance note.
- **OPE/COPPER unusable (already partially true for OPE):** they degrade to citations in
  the schema doc. Nothing at runtime depends on either — that was the point of pulling
  frames and vocabulary rather than URIs and class trees.
- **BioPortal stays bot-blocked:** irrelevant at runtime; the Wayback snapshot and the
  COPPER GitHub OWL are the durable sources.

---

## Sources

- NCI EVS REST API (all SNOMED claims verified live 2026-08-10, terminology
  `snomedct_us`, version `2025_09_01`): https://api-evsrest.nci.nih.gov/api/v1 —
  endpoints used: `/concept/search`, `/concept/snomedct_us/{code}` with
  `include=summary|full|parents|children`, `/children`, `/descendants`, `/pathsToRoot`,
  `/inverseAssociations`.
- EVS Explore (browser spot-checks): https://evsexplore.semantics.cancer.gov/evsexplore/concept/snomedct_us/430725003
- BioPortal OPE summary (live page 403s non-browser clients; metrics from Wayback snapshot
  2024-10-07): https://web.archive.org/web/20241007152257/https://bioportal.bioontology.org/ontologies/OPE
  · live: https://bioportal.bioontology.org/ontologies/OPE
- Bamparopoulos G. et al., "Towards exergaming commons: composing the exergame ontology
  for publishing open game data," J Biomed Semantics 7:4 (2016) — OPE reuse and citation:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4748514/
- Kim H. et al., "Developing a Physical Activity Ontology to Support the Interoperability
  of Physical Activity Data," JMIR 21(4):e12776 (2019) — independent assessment of OPE's
  limitations: https://pmc.ncbi.nlm.nih.gov/articles/PMC6658272/
- COPPER paper: "Development and evaluation of the COntextualised and Personalised
  Physical activity and Exercise Recommendations (COPPER) Ontology," Int J Behav Nutr Phys
  Act (2025), doi:10.1186/s12966-025-01744-5 —
  https://pmc.ncbi.nlm.nih.gov/articles/PMC12054263/
- COPPER OWL (downloaded and inspected 2026-08-10, CC-BY 4.0):
  https://github.com/EBehaviourChange-COPPER/ontology
- SKOS Reference, W3C Recommendation, §10 mapping properties:
  https://www.w3.org/TR/skos-reference/
- PROV-O, W3C Recommendation, Starting Point terms: https://www.w3.org/TR/prov-o/
- SSSOM (noted as mapping-file upgrade path): https://mapping-commons.github.io/sssom/
