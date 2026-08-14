from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import numpy as np
from rapidfuzz.fuzz import token_set_ratio

from ._model import Candidate, Pass, Resolution, Vocabulary, VocabularyConcept

FUZZY_THRESHOLD = 85.0
VECTOR_THRESHOLD = 0.65

_CANDIDATE_LIMIT = 3
_PARENTHETICAL = re.compile(r"\(([^()]*)\)")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class _ExactHit:
    concept: VocabularyConcept
    preferred: bool


@dataclass(frozen=True)
class _ScoredConcept:
    concept: VocabularyConcept
    confidence: float
    term_length_delta: int = 0


def resolve(text: str, vocab: Vocabulary) -> Resolution:
    concepts = tuple(vocab.concepts())
    token_aliases = dict(vocab.token_aliases())
    alias_lengths = tuple(sorted({len(alias) for alias in token_aliases}, reverse=True))
    full_text, stripped_text, modifiers = _mention_parts(
        text, token_aliases, alias_lengths
    )
    index = _exact_index(concepts, token_aliases, alias_lengths)

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

    fuzzy_ranked = _rank_fuzzy(
        concepts,
        tuple(dict.fromkeys((full_text, stripped_text))),
        token_aliases,
        alias_lengths,
    )
    if fuzzy_ranked and fuzzy_ranked[0].confidence >= FUZZY_THRESHOLD / 100:
        return _resolution(
            text,
            modifiers,
            "fuzzy",
            fuzzy_ranked,
        )

    vector_ranked = _rank_vector(stripped_text or full_text, concepts, vocab)
    if vector_ranked and vector_ranked[0].confidence >= VECTOR_THRESHOLD:
        return _resolution(
            text,
            modifiers,
            "vector",
            vector_ranked,
        )

    candidates = vector_ranked or fuzzy_ranked
    return Resolution(
        concept_id=None,
        confidence=0.0,
        pass_="none",
        candidates=_candidates(candidates[:_CANDIDATE_LIMIT]),
        raw_text=text,
        modifiers=modifiers,
    )


def _resolution(
    text: str,
    modifiers: tuple[str, ...],
    pass_: Pass,
    ranked: tuple[_ScoredConcept, ...],
) -> Resolution:
    winner = ranked[0]
    return Resolution(
        concept_id=winner.concept.concept_id,
        confidence=winner.confidence,
        pass_=pass_,
        candidates=_candidates(ranked[1 : _CANDIDATE_LIMIT + 1]),
        raw_text=text,
        modifiers=modifiers,
    )


def _rank_fuzzy(
    concepts: tuple[VocabularyConcept, ...],
    normalized_texts: tuple[str, ...],
    token_aliases: dict[tuple[str, ...], tuple[str, ...]],
    alias_lengths: tuple[int, ...],
) -> tuple[_ScoredConcept, ...]:
    texts = tuple(text for text in normalized_texts if text)
    if not texts:
        return ()
    scored = []
    for concept in concepts:
        terms = (concept.preferred_term, *concept.aliases)
        normalized_terms = {
            normalized
            for term in terms
            for normalized in _mention_parts(term, token_aliases, alias_lengths)[:2]
            if normalized
        }
        scored_terms = tuple(
            (
                token_set_ratio(text, term),
                abs(len(text.split()) - len(term.split())),
            )
            for text in texts
            for term in normalized_terms
        )
        score = max(score for score, _ in scored_terms)
        term_length_delta = min(
            delta for candidate_score, delta in scored_terms if candidate_score == score
        )
        scored.append(
            _ScoredConcept(
                concept=concept,
                confidence=score / 100,
                term_length_delta=term_length_delta,
            )
        )
    return _sort_scored(scored)


def _rank_vector(
    text: str,
    concepts: tuple[VocabularyConcept, ...],
    vocab: Vocabulary,
) -> tuple[_ScoredConcept, ...]:
    embeddings = vocab.embeddings()
    if embeddings is None or (query_embedding := embeddings.query(text)) is None:
        return ()

    concept_rows = tuple(
        (concept, embedding)
        for concept in concepts
        if (embedding := embeddings.concept(concept.concept_id)) is not None
    )
    if not concept_rows:
        return ()
    query = np.asarray(query_embedding, dtype=np.float64)
    matrix = np.asarray([embedding for _, embedding in concept_rows], dtype=np.float64)
    if query.ndim != 1 or matrix.ndim != 2 or matrix.shape[1] != query.shape[0]:
        return ()
    query_norm = np.linalg.norm(query)
    concept_norms = np.linalg.norm(matrix, axis=1)
    if query_norm == 0 or np.any(concept_norms == 0):
        return ()
    similarities = (matrix @ query) / (concept_norms * query_norm)
    return _sort_scored(
        [
            _ScoredConcept(
                concept=concept,
                confidence=max(0.0, min(1.0, float(similarity))),
            )
            for (concept, _), similarity in zip(concept_rows, similarities, strict=True)
        ]
    )


def _sort_scored(scored: list[_ScoredConcept]) -> tuple[_ScoredConcept, ...]:
    return tuple(
        sorted(
            scored,
            key=lambda item: (
                -item.confidence,
                item.term_length_delta,
                item.concept.preferred_term.casefold(),
                item.concept.concept_id,
            ),
        )
    )


def _candidates(scored: tuple[_ScoredConcept, ...]) -> tuple[Candidate, ...]:
    return tuple(
        Candidate(
            concept_id=item.concept.concept_id,
            preferred_term=item.concept.preferred_term,
            confidence=item.confidence,
        )
        for item in scored
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
    concepts: tuple[VocabularyConcept, ...],
    token_aliases: dict[tuple[str, ...], tuple[str, ...]],
    alias_lengths: tuple[int, ...],
) -> dict[str, tuple[_ExactHit, ...]]:
    mutable_index: dict[str, list[_ExactHit]] = {}
    for concept in concepts:
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
