from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Any, Self

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ACQUIRE_PATH = REPO_ROOT / "scripts" / "acquire" / "acquire.py"
ACQUIRE_SPEC = importlib.util.spec_from_file_location("acquire", ACQUIRE_PATH)
if ACQUIRE_SPEC is None or ACQUIRE_SPEC.loader is None:
    raise RuntimeError(f"cannot load Acquire module from {ACQUIRE_PATH}")
acquire: ModuleType = importlib.util.module_from_spec(ACQUIRE_SPEC)
ACQUIRE_SPEC.loader.exec_module(acquire)

TEST_VERSION = "20260301"
TEST_RETRIEVED_AT = "2026-08-13"

DEFAULT_FINDING_SITES = {
    acquire.CONDITION_CODES["lateral-ankle-sprain"]: {"71310002"},
    acquire.CONDITION_CODES["nonspecific-low-back-pain"]: {"52612000"},
    acquire.CONDITION_CODES["patellofemoral-pain-syndrome"]: {"129160003"},
    acquire.CONDITION_CODES["shoulder-impingement"]: {"16982005"},
}

SITE_PARENTS = {
    "71310002": acquire.JOINT_CODES["ankle"],
    "129160003": acquire.JOINT_CODES["knee"],
}


def copper_owl() -> bytes:
    rdf_namespace = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    label_tag = "{http://www.w3.org/2000/01/rdf-schema#}label"
    root = ET.Element(f"{{{rdf_namespace}}}RDF")
    for class_id, kind in acquire.COPPER_CLASSES.items():
        element = ET.SubElement(
            root,
            f"{{{rdf_namespace}}}Description",
            {f"{{{rdf_namespace}}}about": class_id},
        )
        ET.SubElement(element, label_tag).text = kind
    for property_id, label in acquire.COPPER_PROPERTIES.items():
        element = ET.SubElement(
            root,
            f"{{{rdf_namespace}}}Description",
            {f"{{{rdf_namespace}}}about": property_id},
        )
        ET.SubElement(element, label_tag).text = label
    return ET.tostring(root)


class FakeAcquisitionClient:
    def __init__(
        self,
        finding_sites: dict[str, set[str]] | None = None,
        copper_sha: str | None = None,
    ) -> None:
        self.finding_sites = (
            DEFAULT_FINDING_SITES if finding_sites is None else finding_sites
        )
        self.descendant_codes = [str(1_000_000_000 + index) for index in range(287)]
        self.owl_bytes = copper_owl()
        actual_sha = hashlib.sha1(
            f"blob {len(self.owl_bytes)}\0".encode() + self.owl_bytes
        ).hexdigest()
        self.copper_sha = copper_sha or actual_sha
        self.copper_download_url = "https://example.test/COPPER.owl"

    def bytes(self, url: str) -> builtins.bytes:
        if url != self.copper_download_url:
            raise AssertionError(f"unexpected byte request: {url}")
        return self.owl_bytes

    def json(self, url: str) -> Any:
        if url == acquire.COPPER_CONTENTS_URL:
            return {
                "download_url": self.copper_download_url,
                "sha": self.copper_sha,
            }
        if "/descendants?" in url:
            return [{"code": code} for code in self.descendant_codes]
        marker = f"/concept/{acquire.EVS_TERMINOLOGY}/"
        if marker not in url:
            raise AssertionError(f"unexpected JSON request: {url}")
        code = url.split(marker, 1)[1].split("?", 1)[0]
        return self.concept_payload(code)

    def concept_payload(self, code: str) -> dict[str, Any]:
        parents = []
        if parent_code := SITE_PARENTS.get(code):
            parents.append(
                {
                    "code": parent_code,
                    "qualifiers": [{"type": "RELA", "value": "isa"}],
                }
            )
        associations = [
            {
                "relatedCode": site_code,
                "qualifiers": [{"type": "RELA", "value": "has_finding_site"}],
            }
            for site_code in sorted(self.finding_sites.get(code, set()), key=int)
        ]
        return {
            "code": code,
            "name": f"Concept {code}",
            "active": True,
            "version": TEST_VERSION,
            "synonyms": [],
            "parents": parents,
            "associations": associations,
        }


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def clinical_finding_reaches_joint(snomed: dict[str, Any], condition_code: str) -> bool:
    joint_ids = {root["id"] for root in snomed["scope_roots"]}
    condition_id = acquire.concept_id(condition_code)
    site_ids = {
        edge["target_id"]
        for edge in snomed["edges"]
        if edge["type"] == "findingSite" and edge["source_id"] == condition_id
    }
    parents_by_id: dict[str, set[str]] = {}
    for edge in snomed["edges"]:
        if edge["type"] == "isA":
            parents_by_id.setdefault(edge["source_id"], set()).add(edge["target_id"])

    seen: set[str] = set()
    frontier = site_ids
    while frontier and not frontier.intersection(joint_ids):
        seen.update(frontier)
        frontier = {
            parent_id
            for child_id in frontier
            for parent_id in parents_by_id.get(child_id, set())
            if parent_id not in seen
        }
    return bool(frontier.intersection(joint_ids))


def test_http_client_retries_with_its_injected_adapter() -> None:
    outcomes: list[urllib.error.URLError | FakeResponse] = [
        urllib.error.URLError("first failure"),
        urllib.error.URLError("second failure"),
        FakeResponse(b'{"ok": true}'),
    ]
    delays: list[float] = []

    def open_url(request: urllib.request.Request, *, timeout: int) -> FakeResponse:
        assert request.full_url == "https://example.test/data"
        assert timeout == 30
        outcome = outcomes.pop(0)
        if isinstance(outcome, urllib.error.URLError):
            raise outcome
        return outcome

    client = acquire.HttpClient(open_url=open_url, sleep=delays.append)

    assert client.json("https://example.test/data") == {"ok": True}
    assert delays == [1, 2]


def test_acquire_snomed_builds_each_clinical_finding_path_to_joint() -> None:
    snomed = acquire.acquire_snomed(
        FakeAcquisitionClient(), TEST_RETRIEVED_AT, workers=2
    )

    assert len(snomed["concepts"]) == 304
    scope_roots = {root["catalog_term"]: root["id"] for root in snomed["scope_roots"]}
    assert scope_roots["lumbar spine"] == acquire.concept_id("52612000")
    assert scope_roots["shoulder"] == acquire.concept_id("16982005")
    for condition_code in acquire.CONDITION_CODES.values():
        assert clinical_finding_reaches_joint(snomed, condition_code)


def test_acquire_snomed_requires_finding_site_for_each_authored_condition() -> None:
    condition_codes = list(acquire.CONDITION_CODES.values())
    finding_sites = {
        condition_codes[0]: {"71310002", "999999991"},
        condition_codes[1]: set(),
        condition_codes[2]: {"129160003"},
        condition_codes[3]: {"16982005"},
    }

    with pytest.raises(acquire.AcquireError, match=condition_codes[1]):
        acquire.acquire_snomed(
            FakeAcquisitionClient(finding_sites), TEST_RETRIEVED_AT, workers=2
        )


def test_acquire_snomed_rejects_clinical_finding_without_joint_path() -> None:
    condition_code = acquire.CONDITION_CODES["shoulder-impingement"]
    finding_sites = DEFAULT_FINDING_SITES | {condition_code: {"999999999"}}

    with pytest.raises(acquire.AcquireError, match=condition_code):
        acquire.acquire_snomed(
            FakeAcquisitionClient(finding_sites), TEST_RETRIEVED_AT, workers=2
        )


def test_build_artifacts_uses_the_acquisition_adapter() -> None:
    artifacts = acquire.build_artifacts(
        FakeAcquisitionClient(), TEST_RETRIEVED_AT, workers=2
    )

    assert set(artifacts) == {
        "copper.json",
        "prov-o.json",
        "skos-mappings.json",
        "snomed-ct.json",
    }
    assert len(artifacts["copper.json"]["classes"]) == len(acquire.COPPER_CLASSES)
    assert len(artifacts["skos-mappings.json"]["mappings"]) == (
        len(acquire.JOINT_CODES) + len(acquire.CONDITION_CODES)
    )


def test_acquire_copper_rejects_bytes_with_wrong_git_sha() -> None:
    client = FakeAcquisitionClient(copper_sha="0" * 40)

    with pytest.raises(acquire.AcquireError, match="Git blob SHA"):
        acquire.acquire_copper(client, TEST_RETRIEVED_AT)


def test_write_artifacts_writes_stable_json_files(tmp_path: Path) -> None:
    artifacts = {
        "first.json": {"name": "first"},
        "second.json": {"name": "second"},
    }

    acquire.write_artifacts(tmp_path / "ontology", artifacts)

    for filename, payload in artifacts.items():
        path = tmp_path / "ontology" / filename
        assert json.loads(path.read_text(encoding="utf-8")) == payload
        assert path.read_bytes().endswith(b"\n")


@pytest.mark.parametrize("condition_code", acquire.CONDITION_CODES.values())
def test_committed_clinical_finding_reaches_joint(condition_code: str) -> None:
    snomed = json.loads(
        (REPO_ROOT / "data" / "ontology" / "snomed-ct.json").read_text(encoding="utf-8")
    )

    assert clinical_finding_reaches_joint(snomed, condition_code)
