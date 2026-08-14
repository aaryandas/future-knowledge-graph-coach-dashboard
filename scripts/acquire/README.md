# Ontology Acquire stage

Run this rare, network-using build step from the repository root:

```sh
python3 scripts/acquire/acquire.py
```

The script reads the fixed SNOMED CT US subset from NCI EVS and the selected COPPER terms
from its published OWL file. It writes four committed files under `data/ontology/`:

- `snomed-ct.json`: `concepts` and `edges` (`isA`, `findingSite`).
- `copper.json`: eight Barrier classes, one ActionPlan class, and the two pattern properties.
- `skos-mappings.json`: one flat `mappings` array for Joint and Injury `exactMatch` edges.
- `prov-o.json`: the PROV-O starting-point `terms` used by provenance traces.

Each file has `artifact_id`, `schema_version`, `version`, and `source` at its root. IDs are
stable ontology or `fkg:` identifiers. The generated files are the runtime inputs; CI and
application boot must not run Acquire or use the network.

The SNOMED snapshot uses the nine catalog Joint concepts and narrow depth-three descendant
subsets. The shoulder and lumbar spine subsets start at their joint structures, while the
catalog Joint grounding uses the broader region concepts that SNOMED assigns as the authored
conditions' finding sites. It also includes the four authored-condition ClinicalFinding
concepts and their `findingSite` AnatomicalStructure concepts. The script verifies that each
ClinicalFinding reaches a Joint through `findingSite` and `isA*`. It stops if EVS changes the
subset far outside its expected size or returns mixed terminology versions, so a refresh
receives human review instead of silently changing the graph.

## Resolver embeddings

Build the resolver's concept embeddings through OpenRouter from the repository root:

```sh
OPENROUTER_API_KEY=... uv run --project backend python scripts/acquire/build_embeddings.py
```

The script sends one string per concept through LangChain `Embeddings` to OpenRouter. Each
string contains the concept name and its aliases, including SNOMED synonyms. It uses
`qwen/qwen3-embedding-4b` in batches and writes one committed JSON file per vocabulary under
`data/resolver-embeddings/`. Review and commit those artifacts after each intentional
vocabulary or model update. A resolver query that uses vector embeddings must use the same
model. Tests use the small committed fixtures under `backend/tests/fixtures/` and never call
OpenRouter.

Railway supplies `OPENROUTER_API_KEY` to the deployed backend from the backend service
variables. The artifact build uses the key to create the committed concept vectors. An ad hoc
or acceptance resolve run can also use the key to embed query text. That run must explicitly
configure the vocabulary with the matching embedding artifact and an OpenRouter embedding
provider.

The deployed generation runtime does not configure an embedding artifact or provider. It
runs the exact and fuzzy passes without vector embeddings and does not make vector queries.
For an explicitly configured local live check, read the variable with the logged-in Railway
CLI from the linked project:

```sh
export OPENROUTER_API_KEY="$(railway variables --service backend --json | jq -r .OPENROUTER_API_KEY)"
```

Do not print or commit the value. CI deliberately leaves this variable empty and does not
call OpenRouter. When a vocabulary has no embedding provider, `resolve(text, vocab)` runs the
exact and fuzzy passes, skips the vector pass, and returns a `Resolution` value instead of
raising an exception. The artifact build command above still requires the key.
