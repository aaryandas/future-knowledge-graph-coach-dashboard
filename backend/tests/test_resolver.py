from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.resolver import ArtifactEmbeddings, ArtifactVocabulary, resolve

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).parent / "cases" / "resolver.json"
EXERCISES_PATH = REPO_ROOT / "data" / "exercises.json"
MEMBER_CONTEXT_PATH = REPO_ROOT / "data" / "member-context.json"
SNOMED_PATH = REPO_ROOT / "data" / "ontology" / "snomed-ct.json"
SYNONYMS_PATH = REPO_ROOT / "data" / "synonyms.json"
EMBEDDINGS_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "resolver-embeddings"
EQUIPMENT_EMBEDDINGS_PATH = EMBEDDINGS_FIXTURE_DIR / "equipment.json"
ANATOMY_EMBEDDINGS_PATH = EMBEDDINGS_FIXTURE_DIR / "anatomical-structure.json"
VOCABULARY_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "resolver-vocabulary.json"
)


class FixtureEmbeddingProvider:
    def __init__(self, path: Path) -> None:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        self.queries: dict[str, tuple[float, ...]] = {
            text: tuple(vector) for text, vector in artifact["queries"].items()
        }

    def embed_query(self, text: str) -> tuple[float, ...] | None:
        return self.queries.get(text)


class OfflineEmbeddingProvider:
    def embed_query(self, text: str) -> None:
        return None


class FailingEmbeddingProvider:
    def embed_query(self, text: str) -> tuple[float, ...]:
        raise ConnectionError("embedding provider is offline")


EQUIPMENT_EMBEDDINGS = ArtifactEmbeddings.from_file(
    EQUIPMENT_EMBEDDINGS_PATH,
    provider=FixtureEmbeddingProvider(EQUIPMENT_EMBEDDINGS_PATH),
)
ANATOMY_EMBEDDINGS = ArtifactEmbeddings.from_file(
    ANATOMY_EMBEDDINGS_PATH,
    provider=FixtureEmbeddingProvider(ANATOMY_EMBEDDINGS_PATH),
)

CASES: list[dict[str, Any]] = json.loads(CASES_PATH.read_text())
VOCABULARIES = {
    "exercise": ArtifactVocabulary.from_file(
        EXERCISES_PATH,
        kind="Exercise",
        synonyms_path=SYNONYMS_PATH,
    ),
    "equipment": ArtifactVocabulary.from_file(
        EXERCISES_PATH,
        kind="Equipment",
        synonyms_path=SYNONYMS_PATH,
        embeddings=EQUIPMENT_EMBEDDINGS,
    ),
    "muscle_group": ArtifactVocabulary.from_file(
        EXERCISES_PATH, kind="MuscleGroup", synonyms_path=SYNONYMS_PATH
    ),
    "snomed_anatomy": ArtifactVocabulary.from_file(
        SNOMED_PATH,
        kind="AnatomicalStructure",
        synonyms_path=SYNONYMS_PATH,
        embeddings=ANATOMY_EMBEDDINGS,
    ),
    "snomed_finding": ArtifactVocabulary.from_file(
        SNOMED_PATH, kind="ClinicalFinding", synonyms_path=SYNONYMS_PATH
    ),
    "fuzzy_floor": ArtifactVocabulary.from_file(
        VOCABULARY_FIXTURE_PATH,
        kind="Exercise",
        synonyms_path=SYNONYMS_PATH,
    ),
}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_resolver_cases(case: dict[str, Any]) -> None:
    resolution = resolve(case["text"], VOCABULARIES[case["vocabulary"]])

    assert resolution.concept_id == case["expected_id"]
    assert resolution.pass_ == case["expected_pass"]
    assert resolution.confidence == pytest.approx(
        case.get("expected_confidence", 1.0 if resolution.concept_id else 0.0)
    )
    assert resolution.raw_text == case["text"]
    assert resolution.modifiers == tuple(case["expected_modifiers"])
    assert all(
        candidate.concept_id != resolution.concept_id
        for candidate in resolution.candidates
    )
    if expected_candidate_id := case.get("expected_candidate_id"):
        assert resolution.candidates[0].concept_id == expected_candidate_id
        assert resolution.candidates[0].confidence == pytest.approx(
            case["expected_candidate_confidence"]
        )


@pytest.mark.parametrize(
    "provider",
    [None, OfflineEmbeddingProvider()],
    ids=["unconfigured", "offline"],
)
def test_vector_pass_skips_cleanly_without_an_embedding(
    provider: OfflineEmbeddingProvider | None,
) -> None:
    embeddings = ArtifactEmbeddings.from_file(
        EQUIPMENT_EMBEDDINGS_PATH,
        provider=provider,
    )
    vocabulary = ArtifactVocabulary.from_file(
        EXERCISES_PATH,
        kind="Equipment",
        synonyms_path=SYNONYMS_PATH,
        embeddings=embeddings,
    )

    resolution = resolve("portable hand weights", vocabulary)

    assert resolution.concept_id is None
    assert resolution.pass_ == "none"


def test_vector_pass_degrades_when_embedding_provider_connection_fails() -> None:
    embeddings = ArtifactEmbeddings.from_file(
        EQUIPMENT_EMBEDDINGS_PATH,
        provider=FailingEmbeddingProvider(),
    )
    vocabulary = ArtifactVocabulary.from_file(
        EXERCISES_PATH,
        kind="Equipment",
        synonyms_path=SYNONYMS_PATH,
        embeddings=embeddings,
    )

    resolution = resolve("portable hand weights", vocabulary)

    assert resolution.concept_id is None
    assert resolution.pass_ == "none"


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
