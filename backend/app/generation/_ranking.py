from dataclasses import dataclass

from app.generation._constants import (
    CAUTION_PENALTY,
    COOL_DOWN_PATTERNS,
    COVERAGE_GAIN_WEIGHT,
    DISLIKE_PENALTY,
    FOCUS_PATTERN_PREFIXES,
    FOCUS_PATTERNS,
    GOAL_MATCH_WEIGHT,
    PRIORITY_TIER_WEIGHT,
    WARM_UP_PATTERNS,
    ZERO_SCORE,
)
from app.generation._model import Candidate, Section
from app.generation.intent import Focus


@dataclass(frozen=True)
class RankedCandidate:
    candidate: Candidate
    score: int
    goal_match: int
    coverage_gain: int
    priority_tier: int
    caution: int
    dislike: int


def eligible_candidates(
    candidates: tuple[Candidate, ...],
    section: Section,
    focus: Focus | None,
) -> tuple[Candidate, ...]:
    return tuple(
        candidate
        for candidate in candidates
        if _passes_hard_filters(candidate)
        and _eligible_for_section(candidate, section)
        and (section != "main" or _matches_focus(candidate, focus))
    )


def rank_candidates(
    candidates: tuple[Candidate, ...], covered_muscle_groups: frozenset[str]
) -> tuple[RankedCandidate, ...]:
    ranked = tuple(_score(candidate, covered_muscle_groups) for candidate in candidates)
    return tuple(
        sorted(
            ranked,
            key=lambda item: (
                -item.score,
                item.candidate.name,
                item.candidate.exercise_id,
            ),
        )
    )


def hard_filter_reason(candidate: Candidate) -> str | None:
    if candidate.verdict.status == "exclude":
        return "Safety verdict excluded the exercise."
    if candidate.explicitly_excluded:
        return "The resolved exclusion removed the exercise."
    if not candidate.has_required_equipment:
        return "Required equipment is unavailable."
    return None


def _passes_hard_filters(candidate: Candidate) -> bool:
    return hard_filter_reason(candidate) is None


def _eligible_for_section(candidate: Candidate, section: Section) -> bool:
    patterns = frozenset(candidate.movement_patterns)
    if section == "warm-up":
        return not patterns.isdisjoint(WARM_UP_PATTERNS)
    if section == "cool-down":
        return not patterns.isdisjoint(COOL_DOWN_PATTERNS)
    return bool(patterns - WARM_UP_PATTERNS - COOL_DOWN_PATTERNS)


def _matches_focus(candidate: Candidate, focus: Focus | None) -> bool:
    if focus is None or focus == "full-body":
        return True

    prefixes = next(
        (
            focus_prefixes
            for candidate_focus, focus_prefixes in FOCUS_PATTERN_PREFIXES
            if candidate_focus == focus
        ),
        (),
    )
    exact_patterns = next(
        (
            patterns
            for candidate_focus, patterns in FOCUS_PATTERNS
            if candidate_focus == focus
        ),
        frozenset(),
    )
    return any(
        pattern in exact_patterns or pattern.startswith(prefixes)
        for pattern in candidate.movement_patterns
    )


def _score(
    candidate: Candidate, covered_muscle_groups: frozenset[str]
) -> RankedCandidate:
    goal_match = GOAL_MATCH_WEIGHT if candidate.goal_match else ZERO_SCORE
    coverage_gain = (
        len(frozenset(candidate.muscle_groups) - covered_muscle_groups)
        * COVERAGE_GAIN_WEIGHT
    )
    priority_tier = candidate.priority_tier * PRIORITY_TIER_WEIGHT
    caution = CAUTION_PENALTY if candidate.verdict.status == "caution" else ZERO_SCORE
    dislike = DISLIKE_PENALTY if candidate.disliked else ZERO_SCORE
    return RankedCandidate(
        candidate=candidate,
        score=goal_match + coverage_gain + priority_tier - caution - dislike,
        goal_match=goal_match,
        coverage_gain=coverage_gain,
        priority_tier=priority_tier,
        caution=caution,
        dislike=dislike,
    )
