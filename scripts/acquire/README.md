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
