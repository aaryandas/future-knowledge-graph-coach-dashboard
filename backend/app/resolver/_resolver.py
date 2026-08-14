from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ._aliases import TOKEN_ALIASES
from ._model import Candidate, Resolution, Vocabulary, VocabularyConcept

_PARENTHETICAL = re.compile(r"\(([^()]*)\)")
_WHITESPACE = re.compile(r"\s+")
_ALIAS_LENGTHS = tuple(sorted({len(alias) for alias in TOKEN_ALIASES}, reverse=True))


@dataclass(frozen=True)
class _ExactHit:
    concept: VocabularyConcept
    preferred: bool


def resolve(text: str, vocab: Vocabulary) -> Resolution:
    full_text, stripped_text, modifiers = _mention_parts(text)
    index = _exact_index(vocab)

    for normalized_text in dict.fromkeys((full_text, stripped_text)):
        if not normalized_text:
            continue
        hits = index.get(normalized_text, ())
        if hits:
            ranked = _rank_exact_hits(hits)
            return Resolution(
                concept_id=ranked[0].concept_id,
                confidence=1.0,
                method="exact",
                candidates=ranked,
                raw_text=text,
                modifiers=modifiers,
            )

    return Resolution(
        concept_id=None,
        confidence=0.0,
        method="none",
        candidates=(),
        raw_text=text,
        modifiers=modifiers,
    )


def _mention_parts(text: str) -> tuple[str, str, tuple[str, ...]]:
    compatible_text = unicodedata.normalize("NFKC", text)
    modifiers = tuple(
        normalized
        for match in _PARENTHETICAL.finditer(compatible_text)
        if (normalized := _normalize_modifier(match.group(1)))
    )
    stripped_text = _PARENTHETICAL.sub(" ", compatible_text)
    return (
        _normalize_match(compatible_text),
        _normalize_match(stripped_text),
        modifiers,
    )


def _normalize_match(text: str) -> str:
    compatible_text = unicodedata.normalize("NFKC", text).lower()
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in compatible_text
    )
    collapsed = _WHITESPACE.sub(" ", without_punctuation).strip()
    return _expand_aliases(collapsed)


def _normalize_modifier(text: str) -> str:
    compatible_text = unicodedata.normalize("NFKC", text).lower()
    return _WHITESPACE.sub(" ", compatible_text).strip()


def _expand_aliases(text: str) -> str:
    tokens = tuple(text.split())
    expanded: list[str] = []
    position = 0
    while position < len(tokens):
        for length in _ALIAS_LENGTHS:
            alias = tokens[position : position + length]
            if replacement := TOKEN_ALIASES.get(alias):
                expanded.extend(replacement)
                position += length
                break
        else:
            expanded.append(tokens[position])
            position += 1
    return " ".join(expanded)


def _exact_index(vocab: Vocabulary) -> dict[str, tuple[_ExactHit, ...]]:
    mutable_index: dict[str, list[_ExactHit]] = {}
    for concept in vocab.concepts():
        terms = ((concept.preferred_term, True),) + tuple(
            (alias, False) for alias in concept.aliases
        )
        for term, preferred in terms:
            full_term, stripped_term, _ = _mention_parts(term)
            for normalized_term in dict.fromkeys((full_term, stripped_term)):
                if normalized_term:
                    mutable_index.setdefault(normalized_term, []).append(
                        _ExactHit(concept=concept, preferred=preferred)
                    )
    return {term: tuple(hits) for term, hits in mutable_index.items()}


def _rank_exact_hits(hits: tuple[_ExactHit, ...]) -> tuple[Candidate, ...]:
    best_by_concept: dict[str, _ExactHit] = {}
    for hit in hits:
        previous = best_by_concept.get(hit.concept.concept_id)
        if previous is None or hit.preferred:
            best_by_concept[hit.concept.concept_id] = hit
    ranked_hits = sorted(
        best_by_concept.values(),
        key=lambda hit: (
            not hit.preferred,
            hit.concept.preferred_term.lower(),
            hit.concept.concept_id,
        ),
    )
    return tuple(
        Candidate(
            concept_id=hit.concept.concept_id,
            preferred_term=hit.concept.preferred_term,
            confidence=1.0,
        )
        for hit in ranked_hits
    )
