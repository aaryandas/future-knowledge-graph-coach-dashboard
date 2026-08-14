from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from langchain_core.embeddings import Embeddings

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_EMBEDDINGS_PATH = REPO_ROOT / "scripts" / "acquire" / "build_embeddings.py"
BUILD_EMBEDDINGS_SPEC = importlib.util.spec_from_file_location(
    "build_embeddings", BUILD_EMBEDDINGS_PATH
)
if BUILD_EMBEDDINGS_SPEC is None or BUILD_EMBEDDINGS_SPEC.loader is None:
    raise RuntimeError(f"cannot load embedding builder from {BUILD_EMBEDDINGS_PATH}")
build_embeddings: ModuleType = importlib.util.module_from_spec(BUILD_EMBEDDINGS_SPEC)
sys.modules[BUILD_EMBEDDINGS_SPEC.name] = build_embeddings
BUILD_EMBEDDINGS_SPEC.loader.exec_module(build_embeddings)


class FakeEmbeddings(Embeddings):
    def __init__(self) -> None:
        self.documents: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.documents.extend(texts)
        return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        raise AssertionError("the build step does not embed queries")


def test_anatomical_structure_embedding_contains_name_and_snomed_synonyms() -> None:
    spec = next(
        spec
        for spec in build_embeddings.VOCABULARIES
        if spec.kind == "AnatomicalStructure"
    )
    concept = next(
        concept
        for concept in build_embeddings.concepts(spec)
        if concept.concept_id == "snomedct:129160003"
    )

    text = build_embeddings.embedding_text(concept)

    assert text.splitlines() == [
        "Name: Structure of patellofemoral joint",
        "Alias: Femoropatellar joint",
        "Alias: Patellofemoral joint",
        "Alias: Structure of patellofemoral joint (body structure)",
    ]


def test_build_embeddings_returns_one_artifact_per_vocabulary() -> None:
    artifacts = build_embeddings.build_artifacts(
        FakeEmbeddings(),
        build_embeddings.OPENROUTER_MODEL,
        batch_size=64,
    )

    assert set(artifacts) == {
        "anatomical-structure.json",
        "clinical-finding.json",
        "equipment.json",
        "exercise.json",
        "joint.json",
        "movement-pattern.json",
        "muscle-group.json",
    }
    assert {artifact["vocabulary"] for artifact in artifacts.values()} == {
        "AnatomicalStructure",
        "ClinicalFinding",
        "Equipment",
        "Exercise",
        "Joint",
        "MovementPattern",
        "MuscleGroup",
    }
