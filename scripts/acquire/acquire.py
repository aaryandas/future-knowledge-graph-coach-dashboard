#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVS_BASE_URL = "https://api-evsrest.nci.nih.gov/api/v1"
EVS_TERMINOLOGY = "snomedct_us"
COPPER_CONTENTS_URL = (
    "https://api.github.com/repos/EBehaviourChange-COPPER/ontology/contents/COPPER.owl"
)
SCHEMA_VERSION = 1
SNOMED_MAX_DEPTH = 3

JOINT_CODES = {
    "ankle": "70258002",
    "cervical spine": "786964009",
    "elbow": "16953009",
    "hip": "24136001",
    "knee": "49076000",
    "lumbar spine": "786966006",
    "shoulder": "31398001",
    "thoracic spine": "786965005",
    "wrist": "74670003",
}

CONDITION_CODES = {
    "lateral-ankle-sprain": "263133002",
    "nonspecific-low-back-pain": "279039007",
    "patellofemoral-pain-syndrome": "430725003",
    "shoulder-impingement": "239960007",
}

COPPER_BASE = "https://github.com/EBehaviourChange-COPPER/ontology/blob/main/"
COPPER_CLASSES = {
    "http://humanbehaviourchange.org/ontology/BCIO_006133": "Barrier",
    "http://purl.obolibrary.org/obo/MFOEM_000080": "Barrier",
    "http://purl.obolibrary.org/obo/MFOEM_000119": "Barrier",
    f"{COPPER_BASE}COPPER_3000": "Barrier",
    f"{COPPER_BASE}COPPER_3005": "Barrier",
    f"{COPPER_BASE}COPPER_3042": "Barrier",
    f"{COPPER_BASE}COPPER_3044": "Barrier",
    f"{COPPER_BASE}COPPER_3048": "Barrier",
    f"{COPPER_BASE}COPPER_0002": "ActionPlan",
}
COPPER_PROPERTIES = {
    f"{COPPER_BASE}COPPER_0004": "hasActionPlan",
    f"{COPPER_BASE}COPPER_0016": "hasBarrier",
}

PROV_TERMS = (
    ("prov:Entity", "class", "Entity"),
    ("prov:Activity", "class", "Activity"),
    ("prov:Agent", "class", "Agent"),
    ("prov:SoftwareAgent", "class", "SoftwareAgent"),
    ("prov:used", "property", "used"),
    ("prov:wasGeneratedBy", "property", "wasGeneratedBy"),
    ("prov:wasDerivedFrom", "property", "wasDerivedFrom"),
    ("prov:wasAssociatedWith", "property", "wasAssociatedWith"),
    ("prov:startedAtTime", "property", "startedAtTime"),
    ("prov:endedAtTime", "property", "endedAtTime"),
)

RDF_ABOUT = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about"
RDFS_DEFINITION = "{http://www.w3.org/2000/01/rdf-schema#}definition"
RDFS_INSTANCE = "{http://www.w3.org/2000/01/rdf-schema#}instance"
RDFS_LABEL = "{http://www.w3.org/2000/01/rdf-schema#}label"
IAO_DEFINITION = "{http://purl.obolibrary.org/obo/}IAO_0000115"
IAO_ALTERNATIVE_TERM = "{http://purl.obolibrary.org/obo/}IAO_0000118"


class AcquireError(RuntimeError):
    pass


class HttpClient:
    def __init__(self) -> None:
        self._headers = {"User-Agent": "future-knowledge-graph-acquire/1"}

    def bytes(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers=self._headers)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return response.read()
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
            ) as error:
                if attempt == 2:
                    raise AcquireError(f"failed to fetch {url}: {error}") from error
                time.sleep(2**attempt)
        raise AssertionError("retry loop did not return or raise")

    def json(self, url: str) -> Any:
        try:
            return json.loads(self.bytes(url))
        except json.JSONDecodeError as error:
            raise AcquireError(f"invalid JSON from {url}: {error}") from error


def evs_url(path: str, **query: str | int) -> str:
    suffix = f"?{urllib.parse.urlencode(query)}" if query else ""
    return f"{EVS_BASE_URL}/{path}{suffix}"


def concept_id(code: str) -> str:
    return f"snomedct:{code}"


def active_synonyms(payload: dict[str, Any]) -> list[str]:
    preferred_term = payload["name"]
    values = {
        synonym["name"].strip()
        for synonym in payload.get("synonyms") or []
        if synonym.get("active", True) and synonym.get("name", "").strip()
    }
    values.discard(preferred_term)
    return sorted(values, key=str.casefold)


def has_qualifier(item: dict[str, Any], value: str) -> bool:
    return any(
        qualifier.get("type") == "RELA" and qualifier.get("value") == value
        for qualifier in item.get("qualifiers") or []
    )


def fetch_concept(client: HttpClient, code: str) -> dict[str, Any]:
    payload = client.json(
        evs_url(f"concept/{EVS_TERMINOLOGY}/{urllib.parse.quote(code)}", include="full")
    )
    if not isinstance(payload, dict) or payload.get("code") != code:
        raise AcquireError(f"EVS returned the wrong concept for {code}")
    if not payload.get("active", True):
        raise AcquireError(f"SNOMED concept {code} is inactive")
    return payload


def fetch_concepts(
    client: HttpClient, codes: set[str], workers: int
) -> dict[str, dict[str, Any]]:
    concepts: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_concept, client, code): code for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            concepts[code] = future.result()
    return concepts


def acquire_snomed(
    client: HttpClient, retrieved_at: str, workers: int
) -> dict[str, Any]:
    descendant_codes: set[str] = set()
    for code in JOINT_CODES.values():
        descendants = client.json(
            evs_url(
                f"concept/{EVS_TERMINOLOGY}/{code}/descendants",
                maxLevel=SNOMED_MAX_DEPTH,
                pageSize=500,
            )
        )
        if not isinstance(descendants, list):
            raise AcquireError(f"EVS descendants for {code} are not an array")
        if len(descendants) == 500:
            raise AcquireError(f"EVS descendants for {code} may be truncated")
        descendant_codes.update(item["code"] for item in descendants)

    initial_codes = set(JOINT_CODES.values()) | set(CONDITION_CODES.values())
    initial_payloads = fetch_concepts(client, initial_codes, workers)

    finding_site_codes = {
        association["relatedCode"]
        for code in CONDITION_CODES.values()
        for association in initial_payloads[code].get("associations") or []
        if has_qualifier(association, "has_finding_site")
    }
    if len(finding_site_codes) != len(CONDITION_CODES):
        raise AcquireError(
            "each authored condition must have one distinct finding site"
        )

    anatomy_codes = set(JOINT_CODES.values()) | descendant_codes | finding_site_codes
    if not 300 <= len(anatomy_codes) <= 500:
        raise AcquireError(
            f"expected about 350 anatomy concepts, received {len(anatomy_codes)}; review the subset"
        )

    missing_codes = (
        anatomy_codes | set(CONDITION_CODES.values())
    ) - initial_payloads.keys()
    payloads = initial_payloads | fetch_concepts(client, missing_codes, workers)
    versions = {payload.get("version") for payload in payloads.values()}
    if len(versions) != 1 or None in versions:
        raise AcquireError(
            f"SNOMED concepts span unexpected versions: {sorted(map(str, versions))}"
        )
    version = versions.pop()

    concepts = []
    for code in sorted(payloads, key=int):
        payload = payloads[code]
        concepts.append(
            {
                "id": concept_id(code),
                "code": code,
                "kind": (
                    "ClinicalFinding"
                    if code in CONDITION_CODES.values()
                    else "AnatomicalStructure"
                ),
                "preferred_term": payload["name"],
                "synonyms": active_synonyms(payload),
            }
        )

    relationships_by_id: dict[str, dict[str, str]] = {}
    for code in sorted(anatomy_codes, key=int):
        for parent in payloads[code].get("parents") or []:
            parent_code = parent["code"]
            if parent_code not in anatomy_codes or not has_qualifier(parent, "isa"):
                continue
            relationship_id = f"snomedct:{code}:isA:{parent_code}"
            relationships_by_id[relationship_id] = {
                "id": relationship_id,
                "source_id": concept_id(code),
                "type": "isA",
                "target_id": concept_id(parent_code),
            }

    for code in sorted(CONDITION_CODES.values(), key=int):
        for association in payloads[code].get("associations") or []:
            if not has_qualifier(association, "has_finding_site"):
                continue
            target_code = association["relatedCode"]
            relationship_id = f"snomedct:{code}:findingSite:{target_code}"
            relationships_by_id[relationship_id] = {
                "id": relationship_id,
                "source_id": concept_id(code),
                "type": "findingSite",
                "target_id": concept_id(target_code),
            }

    return {
        "artifact_id": "ontology:snomedct_us",
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "source": {
            "terminology": EVS_TERMINOLOGY,
            "url": EVS_BASE_URL,
            "retrieved_at": retrieved_at,
        },
        "scope_roots": [
            {
                "id": concept_id(code),
                "catalog_term": term,
                "max_depth": SNOMED_MAX_DEPTH,
            }
            for term, code in sorted(JOINT_CODES.items())
        ],
        "concepts": concepts,
        "relationships": [
            relationships_by_id[key] for key in sorted(relationships_by_id)
        ],
    }


def child_texts(element: ET.Element, tags: set[str]) -> list[str]:
    return [
        child.text.strip()
        for child in element
        if child.tag in tags and child.text and child.text.strip()
    ]


def acquire_copper(client: HttpClient, retrieved_at: str) -> dict[str, Any]:
    metadata = client.json(COPPER_CONTENTS_URL)
    if (
        not isinstance(metadata, dict)
        or not metadata.get("download_url")
        or not metadata.get("sha")
    ):
        raise AcquireError("GitHub returned invalid COPPER.owl metadata")
    owl_bytes = client.bytes(metadata["download_url"])
    if (
        hashlib.sha1(f"blob {len(owl_bytes)}\0".encode() + owl_bytes).hexdigest()
        != metadata["sha"]
    ):
        raise AcquireError("downloaded COPPER.owl does not match its Git blob SHA")

    root = ET.fromstring(owl_bytes)
    elements = {
        element.attrib[RDF_ABOUT]: element
        for element in root
        if RDF_ABOUT in element.attrib
    }

    classes = []
    for class_id, kind in sorted(COPPER_CLASSES.items()):
        element = elements.get(class_id)
        if element is None:
            raise AcquireError(f"COPPER class is missing: {class_id}")
        labels = child_texts(element, {RDFS_LABEL})
        if not labels:
            raise AcquireError(f"COPPER class has no label: {class_id}")
        definitions = child_texts(element, {RDFS_DEFINITION, IAO_DEFINITION})
        aliases = child_texts(element, {RDFS_INSTANCE, IAO_ALTERNATIVE_TERM})
        classes.append(
            {
                "id": class_id,
                "kind": kind,
                "preferred_term": labels[0],
                "aliases": sorted(set(aliases) - {labels[0]}, key=str.casefold),
                "definition": definitions[0] if definitions else None,
            }
        )

    properties = []
    for property_id, expected_label in sorted(COPPER_PROPERTIES.items()):
        element = elements.get(property_id)
        labels = child_texts(element, {RDFS_LABEL}) if element is not None else []
        if labels != [expected_label]:
            raise AcquireError(f"COPPER property changed: {property_id}")
        properties.append({"id": property_id, "preferred_term": expected_label})

    return {
        "artifact_id": "ontology:copper",
        "schema_version": SCHEMA_VERSION,
        "version": metadata["sha"],
        "source": {
            "url": metadata["download_url"],
            "license": "CC-BY-4.0",
            "version_kind": "git_blob_sha",
            "retrieved_at": retrieved_at,
        },
        "classes": classes,
        "properties": properties,
    }


def skos_mappings(snomed: dict[str, Any], retrieved_at: str) -> dict[str, Any]:
    concepts = {concept["code"]: concept for concept in snomed["concepts"]}
    source_codes = {
        **{
            f"fkg:joint/{term.replace(' ', '-')}": code
            for term, code in JOINT_CODES.items()
        },
        **{
            f"fkg:injury/{condition}": code
            for condition, code in CONDITION_CODES.items()
        },
    }
    mappings = []
    for source_id, code in sorted(source_codes.items()):
        target_id = concept_id(code)
        mapping_id = f"skos-map:{source_id}:exactMatch:{target_id}"
        mappings.append(
            {
                "id": mapping_id,
                "source_id": source_id,
                "predicate": "skos:exactMatch",
                "target_id": target_id,
                "target_label": concepts[code]["preferred_term"],
                "confidence": 1.0,
            }
        )
    return {
        "artifact_id": "ontology:skos-mappings",
        "schema_version": SCHEMA_VERSION,
        "version": snomed["version"],
        "source": {
            "standard": "SKOS",
            "url": "https://www.w3.org/TR/skos-reference/",
            "snomedct_version": snomed["version"],
            "verified_at": retrieved_at,
        },
        "@context": {
            "fkg": "https://example.com/fkg/",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "snomedct": "http://snomed.info/id/",
        },
        "mappings": mappings,
    }


def prov_terms() -> dict[str, Any]:
    return {
        "artifact_id": "ontology:prov-o",
        "schema_version": SCHEMA_VERSION,
        "version": "2013-04-30",
        "source": {
            "standard": "PROV-O",
            "url": "https://www.w3.org/TR/prov-o/",
        },
        "context": {"prov": "http://www.w3.org/ns/prov#"},
        "terms": [
            {
                "id": term_id,
                "kind": kind,
                "preferred_term": preferred_term,
                "iri": f"http://www.w3.org/ns/prov#{preferred_term}",
            }
            for term_id, kind, preferred_term in PROV_TERMS
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Refresh the committed ontology snapshot artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "data" / "ontology",
        help="artifact directory (default: data/ontology)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="parallel NCI EVS concept requests (default: 12)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.workers < 1 or args.workers > 24:
        raise AcquireError("--workers must be between 1 and 24")

    retrieved_at = datetime.now(UTC).date().isoformat()
    client = HttpClient()
    snomed = acquire_snomed(client, retrieved_at, args.workers)
    copper = acquire_copper(client, retrieved_at)
    artifacts = {
        "snomed-ct.json": snomed,
        "copper.json": copper,
        "skos-mappings.json": skos_mappings(snomed, retrieved_at),
        "prov-o.json": prov_terms(),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in artifacts.items():
        write_json(args.output_dir / filename, payload)

    anatomy_count = sum(
        concept["kind"] == "AnatomicalStructure" for concept in snomed["concepts"]
    )
    finding_count = len(snomed["concepts"]) - anatomy_count
    print(
        f"wrote {len(artifacts)} artifacts: {anatomy_count} anatomy concepts, "
        f"{finding_count} clinical findings, {len(copper['classes'])} COPPER classes"
    )


if __name__ == "__main__":
    main()
