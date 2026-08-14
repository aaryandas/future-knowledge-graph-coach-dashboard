from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ._model import Candidate, Resolution, Vocabulary, VocabularyConcept

_PARENTHETICAL = re.compile(r"\(([^()]*)\)")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class _ExactHit:
    concept: VocabularyConcept
    preferred: bool


def resolve(text: str, vocab: Vocabulary) -> Resolution:
    token_aliases = dict(vocab.token_aliases())
    alias_lengths = tuple(sorted({len(alias) for alias in token_aliases}, reverse=True))
    full_text, stripped_text, modifiers = _mention_parts(
        text, token_aliases, alias_lengths
    )
    index = _exact_index(vocab, token_aliases, alias_lengths)

    for normalized_text in dict.fromkeys((full_text, stripped_text)):
        if not normalized_text:
            continue
        hits = index.get(normalized_text, ())
        if hits:
            ranked = _rank_exact_hits(hits)
            return Resolution(
                concept_id=ranked[0].concept_id,
                confidence=1.0,
                pass_="exact",
                candidates=ranked[1:],
                raw_text=text,
                modifiers=modifiers,
            )

    return Resolution(
        concept_id=None,
        confidence=0.0,
        pass_="none",
        candidates=(),
        raw_text=text,
        modifiers=modifiers,
    )


def _mention_parts(
    text: str,
    token_aliases: dict[tuple[str, ...], tuple[str, ...]],
    alias_lengths: tuple[int, ...],
) -> tuple[str, str, tuple[str, ...]]:
    compatible_text = unicodedata.normalize("NFKC", text)
    modifiers = tuple(
        normalized
        for match in _PARENTHETICAL.finditer(compatible_text)
        if (normalized := _normalize_modifier(match.group(1)))
    )
    stripped_text = _PARENTHETICAL.sub(" ", compatible_text)
    return (
        _normalize_match(compatible_text, token_aliases, alias_lengths),
        _normalize_match(stripped_text, token_aliases, alias_lengths),
        modifiers,
    )


def _normalize_match(
    text: str,
    token_aliases: dict[tuple[str, ...], tuple[str, ...]],
    alias_lengths: tuple[int, ...],
) -> str:
    compatible_text = unicodedata.normalize("NFKC", text).lower()
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in compatible_text
    )
    collapsed = _WHITESPACE.sub(" ", without_punctuation).strip()
    return _expand_aliases(collapsed, token_aliases, alias_lengths)


def _normalize_modifier(text: str) -> str:
    compatible_text = unicodedata.normalize("NFKC", text).lower()
    return _WHITESPACE.sub(" ", compatible_text).strip()


def _expand_aliases(
    text: str,
    token_aliases: dict[tuple[str, ...], tuple[str, ...]],
    alias_lengths: tuple[int, ...],
) -> str:
    tokens = tuple(text.split())
    expanded: list[str] = []
    position = 0
    while position < len(tokens):
        for length in alias_lengths:
            alias = tokens[position : position + length]
            if replacement := token_aliases.get(alias):
                expanded.extend(replacement)
                position += length
                break
        else:
            expanded.append(tokens[position])
            position += 1
    return " ".join(expanded)


def _exact_index(
    vocab: Vocabulary,
    token_aliases: dict[tuple[str, ...], tuple[str, ...]],
    alias_lengths: tuple[int, ...],
) -> dict[str, tuple[_ExactHit, ...]]:
    mutable_index: dict[str, list[_ExactHit]] = {}
    for concept in vocab.concepts():
        terms = ((concept.preferred_term, True),) + tuple(
            (alias, False) for alias in concept.aliases
        )
        for term, preferred in terms:
            full_term, stripped_term, _ = _mention_parts(
                term, token_aliases, alias_lengths
            )
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
