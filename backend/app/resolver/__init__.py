"""Resolve free-text mentions against an injected vocabulary."""

from ._artifacts import ArtifactVocabulary
from ._model import (
    Candidate,
    Resolution,
    ResolutionMethod,
    Vocabulary,
    VocabularyConcept,
)
from ._resolver import resolve

__all__ = [
    "ArtifactVocabulary",
    "Candidate",
    "Resolution",
    "ResolutionMethod",
    "Vocabulary",
    "VocabularyConcept",
    "resolve",
]
