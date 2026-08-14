#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.resolver import (
    EMBEDDING_SCHEMA_VERSION,
    ArtifactVocabulary,
    KG1NodeKind,
    VocabularyConcept,
)

DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "resolver-embeddings"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "qwen/qwen3-embedding-0.6b"
DETERMINISTIC_MODEL = "deterministic/sha256-v1"
SYNONYMS_PATH = REPO_ROOT / "data" / "synonyms.json"
OPENROUTER_SOURCE = {
    "provider": "OpenRouter",
    "url": f"{OPENROUTER_BASE_URL}/embeddings",
}
DETERMINISTIC_SOURCE = {
    "provider": "deterministic",
    "algorithm": "sha256 byte projection",
}


@dataclass(frozen=True)
class VocabularySpec:
    filename: str
    path: Path
    kind: KG1NodeKind


class DeterministicEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [(component - 127.5) / 127.5 for component in digest]


VOCABULARIES = (
    VocabularySpec("exercise.json", REPO_ROOT / "data" / "exercises.json", "Exercise"),
    VocabularySpec(
        "muscle-group.json",
        REPO_ROOT / "data" / "exercises.json",
        "MuscleGroup",
    ),
    VocabularySpec("joint.json", REPO_ROOT / "data" / "exercises.json", "Joint"),
    VocabularySpec(
        "movement-pattern.json",
        REPO_ROOT / "data" / "exercises.json",
        "MovementPattern",
    ),
    VocabularySpec(
        "equipment.json", REPO_ROOT / "data" / "exercises.json", "Equipment"
    ),
    VocabularySpec(
        "anatomical-structure.json",
        REPO_ROOT / "data" / "ontology" / "snomed-ct.json",
        "AnatomicalStructure",
    ),
    VocabularySpec(
        "clinical-finding.json",
        REPO_ROOT / "data" / "ontology" / "snomed-ct.json",
        "ClinicalFinding",
    ),
)


def concepts(spec: VocabularySpec) -> tuple[VocabularyConcept, ...]:
    vocabulary = ArtifactVocabulary.from_file(
        spec.path,
        kind=spec.kind,
        synonyms_path=SYNONYMS_PATH,
    )
    return tuple(
        sorted(
            vocabulary.concepts(),
            key=lambda concept: (concept.preferred_term.casefold(), concept.concept_id),
        )
    )


def embedding_text(concept: VocabularyConcept) -> str:
    terms = dict.fromkeys((concept.preferred_term, *concept.aliases))
    return "\n".join(
        (
            f"Name: {concept.preferred_term}",
            *(f"Alias: {term}" for term in terms if term != concept.preferred_term),
        )
    )


def build_artifact(
    spec: VocabularySpec,
    provider: Embeddings,
    model: str,
    batch_size: int,
    source: Mapping[str, str] = OPENROUTER_SOURCE,
) -> dict[str, object]:
    vocabulary_concepts = concepts(spec)
    concept_embeddings: dict[str, list[float]] = {}
    dimensions: int | None = None

    for start in range(0, len(vocabulary_concepts), batch_size):
        batch = vocabulary_concepts[start : start + batch_size]
        vectors = provider.embed_documents(
            [embedding_text(concept) for concept in batch]
        )
        if len(vectors) != len(batch):
            raise RuntimeError("OpenRouter did not return the requested embeddings")
        for concept, vector in zip(batch, vectors, strict=True):
            if dimensions is None:
                dimensions = len(vector)
            if len(vector) != dimensions:
                raise RuntimeError("OpenRouter returned mixed embedding dimensions")
            concept_embeddings[concept.concept_id] = vector

    if dimensions is None:
        raise RuntimeError(f"no resolver concepts were found for {spec.kind}")
    vocabulary_id = spec.filename.removesuffix(".json")
    return {
        "artifact_id": f"resolver:{vocabulary_id}-embeddings",
        "schema_version": EMBEDDING_SCHEMA_VERSION,
        "vocabulary": spec.kind,
        "model": model,
        "dimensions": dimensions,
        "source": dict(source),
        "embeddings": dict(sorted(concept_embeddings.items())),
    }


def build_artifacts(
    provider: Embeddings,
    model: str,
    batch_size: int,
    source: Mapping[str, str] = OPENROUTER_SOURCE,
) -> dict[str, dict[str, object]]:
    return {
        spec.filename: build_artifact(spec, provider, model, batch_size, source)
        for spec in VOCABULARIES
    }


def write_artifacts(
    output_dir: Path,
    artifacts: dict[str, dict[str, object]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, artifact in artifacts.items():
        (output_dir / filename).write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def openrouter_embeddings(model: str) -> Embeddings:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required to build embeddings")
    return OpenAIEmbeddings(
        model=model,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        check_embedding_ctx_length=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the committed resolver embedding artifacts."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", default=OPENROUTER_MODEL)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="build reproducible local vectors without a provider key",
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    if args.deterministic:
        provider = DeterministicEmbeddings()
        model = DETERMINISTIC_MODEL
        source = DETERMINISTIC_SOURCE
    else:
        provider = openrouter_embeddings(args.model)
        model = args.model
        source = OPENROUTER_SOURCE
    artifacts = build_artifacts(provider, model, args.batch_size, source)
    write_artifacts(args.output_dir, artifacts)
    count = sum(len(artifact["embeddings"]) for artifact in artifacts.values())
    print(f"wrote {count} embeddings across {len(artifacts)} vocabularies")


if __name__ == "__main__":
    main()
