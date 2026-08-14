"""Resolve free-text mentions against an injected vocabulary."""

from ._artifacts import ArtifactVocabulary, KG1NodeKind
from ._embeddings import EMBEDDING_SCHEMA_VERSION, ArtifactEmbeddings
from ._model import (
    Candidate,
    Pass,
    Resolution,
    Vocabulary,
    VocabularyConcept,
)
from ._resolver import resolve

__all__ = [
    "EMBEDDING_SCHEMA_VERSION",
    "ArtifactEmbeddings",
    "ArtifactVocabulary",
    "Candidate",
    "KG1NodeKind",
    "Pass",
    "Resolution",
    "Vocabulary",
    "VocabularyConcept",
    "resolve",
]
