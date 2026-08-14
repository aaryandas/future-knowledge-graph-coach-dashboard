from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.resolver import ArtifactVocabulary, resolve

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).parent / "cases" / "resolver.json"
EXERCISES_PATH = REPO_ROOT / "data" / "exercises.json"
MEMBER_CONTEXT_PATH = REPO_ROOT / "data" / "member-context.json"
SNOMED_PATH = REPO_ROOT / "data" / "ontology" / "snomed-ct.json"

CASES: list[dict[str, Any]] = json.loads(CASES_PATH.read_text())
VOCABULARIES = {
    "exercise": ArtifactVocabulary.from_file(EXERCISES_PATH, kind="Exercise"),
    "equipment": ArtifactVocabulary.from_file(EXERCISES_PATH, kind="Equipment"),
    "muscle_group": ArtifactVocabulary.from_file(EXERCISES_PATH, kind="MuscleGroup"),
    "snomed_anatomy": ArtifactVocabulary.from_file(
        SNOMED_PATH, kind="AnatomicalStructure"
    ),
    "snomed_finding": ArtifactVocabulary.from_file(SNOMED_PATH, kind="ClinicalFinding"),
}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_resolver_cases(case: dict[str, Any]) -> None:
    resolution = resolve(case["text"], VOCABULARIES[case["vocabulary"]])

    assert resolution.concept_id == case["expected_id"]
    assert resolution.method == case["expected_method"]
    assert resolution.confidence == (1.0 if resolution.concept_id else 0.0)
    assert resolution.raw_text == case["text"]
    assert resolution.modifiers == tuple(case["expected_modifiers"])
    if resolution.concept_id is not None:
        assert resolution.candidates[0].concept_id == resolution.concept_id


def test_cases_include_each_real_member_string() -> None:
    member = json.loads(MEMBER_CONTEXT_PATH.read_text())
    member_strings = {
        *member["preferences"]["dislikes"],
        *member["equipment_available"],
        *(
            exercise
            for workout in member["workout_history"]
            for exercise in workout["exercises"]
        ),
    }
    covered_member_strings = {
        case["text"] for case in CASES if case.get("source") == "member-context"
    }

    assert covered_member_strings == member_strings
