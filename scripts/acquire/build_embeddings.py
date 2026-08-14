#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.resolver import (
    EMBEDDING_SCHEMA_VERSION,
    OPENROUTER_MODEL,
    ArtifactVocabulary,
    KG1NodeKind,
    OpenRouterEmbeddingProvider,
    VocabularyConcept,
)

DEFAULT_OUTPUT = REPO_ROOT / "data" / "resolver-embeddings.json"
SYNONYMS_PATH = REPO_ROOT / "data" / "synonyms.json"
VOCABULARIES: tuple[tuple[Path, KG1NodeKind], ...] = (
    (REPO_ROOT / "data" / "exercises.json", "Exercise"),
    (REPO_ROOT / "data" / "exercises.json", "MuscleGroup"),
    (REPO_ROOT / "data" / "exercises.json", "Joint"),
    (REPO_ROOT / "data" / "exercises.json", "MovementPattern"),
    (REPO_ROOT / "data" / "exercises.json", "Equipment"),
    (REPO_ROOT / "data" / "ontology" / "snomed-ct.json", "AnatomicalStructure"),
    (REPO_ROOT / "data" / "ontology" / "snomed-ct.json", "ClinicalFinding"),
)


def concepts() -> tuple[VocabularyConcept, ...]:
    by_id: dict[str, VocabularyConcept] = {}
    for path, kind in VOCABULARIES:
        vocabulary = ArtifactVocabulary.from_file(
            path,
            kind=kind,
            synonyms_path=SYNONYMS_PATH,
        )
        for concept in vocabulary.concepts():
            previous = by_id.get(concept.concept_id)
            if (
                previous is not None
                and previous.preferred_term != concept.preferred_term
            ):
                raise ValueError(
                    f"concept {concept.concept_id} has conflicting preferred terms"
                )
            by_id[concept.concept_id] = concept
    return tuple(
        sorted(
            by_id.values(),
            key=lambda concept: (concept.preferred_term.casefold(), concept.concept_id),
        )
    )


def build_artifact(model: str, batch_size: int) -> dict[str, object]:
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError("OPENROUTER_API_KEY is required to build embeddings")
    provider = OpenRouterEmbeddingProvider.from_env()
    vocabulary_concepts = concepts()
    embeddings: dict[str, list[float]] = {}
    dimensions: int | None = None

    for start in range(0, len(vocabulary_concepts), batch_size):
        batch = vocabulary_concepts[start : start + batch_size]
        vectors = provider.embed(
            tuple(concept.preferred_term for concept in batch),
            model=model,
        )
        if vectors is None or len(vectors) != len(batch):
            raise RuntimeError("OpenRouter did not return the requested embeddings")
        for concept, vector in zip(batch, vectors, strict=True):
            if dimensions is None:
                dimensions = len(vector)
            if len(vector) != dimensions:
                raise RuntimeError("OpenRouter returned mixed embedding dimensions")
            embeddings[concept.concept_id] = list(vector)

    if dimensions is None:
        raise RuntimeError("no resolver concepts were found")
    return {
        "artifact_id": "resolver:concept-embeddings",
        "schema_version": EMBEDDING_SCHEMA_VERSION,
        "model": model,
        "dimensions": dimensions,
        "source": {
            "provider": "OpenRouter",
            "url": "https://openrouter.ai/api/v1/embeddings",
        },
        "embeddings": dict(sorted(embeddings.items())),
    }


def write_artifact(path: Path, artifact: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the committed resolver concept embedding artifact."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=OPENROUTER_MODEL)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    artifact = build_artifact(args.model, args.batch_size)
    write_artifact(args.output, artifact)
    print(f"wrote {len(artifact['embeddings'])} embeddings to {args.output}")


if __name__ == "__main__":
    main()
