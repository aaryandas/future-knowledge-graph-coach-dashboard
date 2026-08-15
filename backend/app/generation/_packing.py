from dataclasses import dataclass, replace
from itertools import combinations
from typing import Literal, cast

from app.generation._constants import (
    COOL_DOWN_HOLD_MINUTES,
    COOL_DOWN_REST_MINUTES,
    COOL_DOWN_SETS,
    MAIN_HOLD_MINUTES,
    MAIN_REDUCED_SETS,
    MAIN_REPS,
    MAIN_REST_MINUTES,
    MAIN_SETS,
    MINIMUM_SECTION_ENTRIES,
    MINIMUM_WINDOW_MINUTES,
    PER_SIDE_COUNT,
    REST_INTERVAL_OFFSET,
    SECTION_ORDER,
    SECTION_SPLITS,
    SINGLE_SIDE_COUNT,
    TIME_COMPARISON_TOLERANCE,
    TIME_DECIMAL_PLACES,
    WARM_UP_HOLD_MINUTES,
    WARM_UP_REPS,
    WARM_UP_REST_MINUTES,
    WARM_UP_SETS,
    ZERO_MINUTES,
)
from app.generation._model import Candidate, Plan, PlanEntry, PlanSection, Section
from app.generation._ranking import (
    RankedCandidate,
    eligible_candidates,
    hard_filter_reason,
    rank_candidates,
)
from app.generation._trace import PackingTraceEvent, TraceEvent
from app.generation.intent import Focus, Intent

type PackingFailureReason = Literal[
    "empty-section",
    "minimum-plan-exceeds-window",
]


@dataclass(frozen=True)
class PackingFailure:
    reason: PackingFailureReason
    message: str
    section: Section | None
    events: tuple[TraceEvent, ...]


@dataclass(frozen=True)
class _PackedEntry:
    candidate: Candidate
    entry: PlanEntry
    ranking: RankedCandidate


def pack(
    candidates: tuple[Candidate, ...], intent: Intent, window: int
) -> tuple[Plan, tuple[TraceEvent, ...]] | PackingFailure:
    """Pack one deterministic three-section plan into the supported window."""
    _validate_inputs(candidates, window)
    events = _hard_filter_events(candidates)
    used_exercise_ids: set[str] = set()
    packed_by_section: dict[Section, list[_PackedEntry]] = {}
    split_by_section = dict(SECTION_SPLITS)

    for section_index, section_name in enumerate(SECTION_ORDER):
        section = cast(Section, section_name)
        available_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.exercise_id not in used_exercise_ids
        )
        section_candidates = eligible_candidates(
            available_candidates,
            section,
            intent.focus,
        )
        packed_entries, selection_events = _select_section(
            section_candidates,
            section,
            window * split_by_section[section],
            available_candidates=available_candidates,
            later_sections=SECTION_ORDER[section_index + 1 :],
            focus=intent.focus,
        )
        if len(packed_entries) < MINIMUM_SECTION_ENTRIES:
            return PackingFailure(
                reason="empty-section",
                message=f"No eligible exercise is available for the {section} section.",
                section=section,
                events=tuple(events),
            )
        packed_by_section[section] = packed_entries
        used_exercise_ids.update(
            packed_entry.candidate.exercise_id for packed_entry in packed_entries
        )
        events.extend(selection_events)

    cut_events = _fit_window(packed_by_section, window)
    events.extend(cut_events)
    sections = {
        section: _plan_section(section, packed_by_section[section])
        for section in SECTION_ORDER
    }
    packed_minutes = _round_minutes(
        sum(plan_section.minutes for plan_section in sections.values())
    )
    if packed_minutes > window + TIME_COMPARISON_TOLERANCE:
        return PackingFailure(
            reason="minimum-plan-exceeds-window",
            message="The minimum three-section plan does not fit the requested window.",
            section=None,
            events=tuple(events),
        )

    return (
        Plan(
            warm_up=sections["warm-up"],
            main=sections["main"],
            cool_down=sections["cool-down"],
            requested_minutes=window,
            packed_minutes=packed_minutes,
        ),
        tuple(events),
    )


def _validate_inputs(candidates: tuple[Candidate, ...], window: int) -> None:
    if window < MINIMUM_WINDOW_MINUTES:
        raise ValueError(
            f"Packing window must be at least {MINIMUM_WINDOW_MINUTES} minutes"
        )
    exercise_ids: set[str] = set()
    for candidate in candidates:
        if candidate.exercise_id in exercise_ids:
            raise ValueError(f"Duplicate packing candidate: {candidate.exercise_id}")
        exercise_ids.add(candidate.exercise_id)
        if candidate.verdict.exercise_id != candidate.exercise_id:
            raise ValueError("Candidate and verdict exercise ids differ")
        if candidate.is_reps and candidate.estimated_rep_duration <= ZERO_MINUTES:
            raise ValueError("Rep-based candidate must have a positive rep duration")
        if not candidate.is_reps and not candidate.is_duration:
            raise ValueError("Candidate supports neither reps nor duration")
        one_side_fields = (
            candidate.is_bilateral,
            candidate.side is not None,
            candidate.bilateral_pair_id is not None,
        )
        if any(one_side_fields) and not all(one_side_fields):
            raise ValueError("One-side candidate fields disagree")


def _hard_filter_events(candidates: tuple[Candidate, ...]) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for candidate in sorted(candidates, key=lambda item: (item.name, item.exercise_id)):
        reason = hard_filter_reason(candidate)
        if reason is None:
            continue
        events.append(
            PackingTraceEvent(
                action="filtered",
                section=None,
                exercise_id=candidate.exercise_id,
                reason=reason,
                used=(candidate.exercise_id,),
            )
        )
    return events


def _select_section(
    candidates: tuple[Candidate, ...],
    section: Section,
    target_minutes: float,
    *,
    available_candidates: tuple[Candidate, ...],
    later_sections: tuple[Section, ...],
    focus: Focus | None,
) -> tuple[list[_PackedEntry], list[TraceEvent]]:
    remaining = candidates
    selected: list[_PackedEntry] = []
    events: list[TraceEvent] = []
    covered_muscle_groups: frozenset[str] = frozenset()
    remaining_minutes = target_minutes

    while remaining and remaining_minutes > TIME_COMPARISON_TOLERANCE:
        ranked = rank_candidates(remaining, covered_muscle_groups)
        reservable = tuple(
            ranked_candidate
            for ranked_candidate in ranked
            if _can_reserve_later_sections(
                tuple(
                    candidate
                    for candidate in available_candidates
                    if candidate.exercise_id != ranked_candidate.candidate.exercise_id
                ),
                later_sections,
                focus,
            )
        )
        fitting = next(
            (
                ranked_candidate
                for ranked_candidate in reservable
                if _entry(ranked_candidate.candidate, section).minutes
                <= remaining_minutes + TIME_COMPARISON_TOLERANCE
            ),
            None,
        )
        if fitting is None:
            if selected:
                break
            fitting = next(iter(reservable), None)
        if fitting is None:
            break

        plan_entry = _entry(fitting.candidate, section)
        selected.append(
            _PackedEntry(
                candidate=fitting.candidate,
                entry=plan_entry,
                ranking=fitting,
            )
        )
        events.append(_selection_event(fitting, section))
        remaining_minutes = _round_minutes(remaining_minutes - plan_entry.minutes)
        covered_muscle_groups = covered_muscle_groups.union(
            fitting.candidate.muscle_groups
        )
        remaining = tuple(
            candidate
            for candidate in remaining
            if candidate.exercise_id != fitting.candidate.exercise_id
        )
        available_candidates = tuple(
            candidate
            for candidate in available_candidates
            if candidate.exercise_id != fitting.candidate.exercise_id
        )

    return selected, events


def _can_reserve_later_sections(
    candidates: tuple[Candidate, ...],
    later_sections: tuple[Section, ...],
    focus: Focus | None,
) -> bool:
    def reserve(section_index: int, used_exercise_ids: frozenset[str]) -> bool:
        if section_index == len(later_sections):
            return True
        section = later_sections[section_index]
        eligible = tuple(
            candidate
            for candidate in eligible_candidates(candidates, section, focus)
            if candidate.exercise_id not in used_exercise_ids
        )
        return any(
            reserve(
                section_index + 1,
                used_exercise_ids.union(
                    candidate.exercise_id for candidate in selection
                ),
            )
            for selection in combinations(eligible, MINIMUM_SECTION_ENTRIES)
        )

    return reserve(0, frozenset())


def _selection_event(ranking: RankedCandidate, section: Section) -> PackingTraceEvent:
    return PackingTraceEvent(
        action="selected",
        section=section,
        exercise_id=ranking.candidate.exercise_id,
        reason=(
            f"score {ranking.score}: goal match {ranking.goal_match} + coverage gain "
            f"{ranking.coverage_gain} + priority tier {ranking.priority_tier} - caution "
            f"{ranking.caution} - dislike {ranking.dislike}."
        ),
        used=(ranking.candidate.exercise_id,),
        score=ranking.score,
    )


def _entry(
    candidate: Candidate, section: Section, *, sets_override: int | None = None
) -> PlanEntry:
    if section == "cool-down":
        sets = COOL_DOWN_SETS
        reps = None
        hold_minutes = COOL_DOWN_HOLD_MINUTES
        rest_minutes = COOL_DOWN_REST_MINUTES
    elif candidate.is_reps:
        if section == "warm-up":
            sets = WARM_UP_SETS
            reps = WARM_UP_REPS
            rest_minutes = WARM_UP_REST_MINUTES
        else:
            sets = sets_override or MAIN_SETS
            reps = MAIN_REPS
            rest_minutes = MAIN_REST_MINUTES
        hold_minutes = None
    else:
        sets = WARM_UP_SETS if section == "warm-up" else COOL_DOWN_SETS
        reps = None
        hold_minutes = (
            WARM_UP_HOLD_MINUTES if section == "warm-up" else MAIN_HOLD_MINUTES
        )
        rest_minutes = (
            WARM_UP_REST_MINUTES if section == "warm-up" else MAIN_REST_MINUTES
        )

    minutes = _entry_minutes(
        sets=sets,
        reps=reps,
        hold_minutes=hold_minutes,
        rest_minutes=rest_minutes,
        rep_duration=candidate.estimated_rep_duration,
        per_side=candidate.is_bilateral,
    )
    return PlanEntry(
        exercise_id=candidate.exercise_id,
        name=candidate.name,
        sets=sets,
        reps=reps,
        hold_minutes=hold_minutes,
        rest_minutes=rest_minutes,
        per_side=candidate.is_bilateral,
        supports_weight=candidate.supports_weight,
        verdict=candidate.verdict.status,
        caution_note=_caution_note(candidate),
        minutes=minutes,
    )


def _entry_minutes(
    *,
    sets: int,
    reps: int | None,
    hold_minutes: float | None,
    rest_minutes: float,
    rep_duration: float,
    per_side: bool,
) -> float:
    side_count = PER_SIDE_COUNT if per_side else SINGLE_SIDE_COUNT
    if reps is not None:
        work_minutes = side_count * sets * reps * rep_duration
        rest_intervals = side_count * sets - REST_INTERVAL_OFFSET
    else:
        if hold_minutes is None:
            raise RuntimeError("Duration entry has no hold time")
        work_minutes = side_count * hold_minutes
        rest_intervals = side_count - REST_INTERVAL_OFFSET
    return _round_minutes(work_minutes + rest_intervals * rest_minutes)


def _caution_note(candidate: Candidate) -> str | None:
    if candidate.verdict.status != "caution":
        return None
    decision = next(
        (
            decision
            for decision in candidate.verdict.decisions
            if decision.status == "caution"
        ),
        None,
    )
    if decision is None:
        raise RuntimeError("Caution verdict has no caution decision")
    return decision.reason


def _fit_window(
    packed_by_section: dict[Section, list[_PackedEntry]], window: int
) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    _drop_entries_until_fit(packed_by_section, "cool-down", window, events)
    _drop_entries_until_fit(packed_by_section, "warm-up", window, events)
    _reduce_main_sets_until_fit(packed_by_section, window, events)
    _drop_entries_until_fit(packed_by_section, "main", window, events)
    return events


def _drop_entries_until_fit(
    packed_by_section: dict[Section, list[_PackedEntry]],
    section: Section,
    window: int,
    events: list[TraceEvent],
) -> None:
    entries = packed_by_section[section]
    while (
        _packed_minutes(packed_by_section) > window + TIME_COMPARISON_TOLERANCE
        and len(entries) > MINIMUM_SECTION_ENTRIES
    ):
        dropped = entries.pop()
        events.append(
            PackingTraceEvent(
                action="cut",
                section=section,
                exercise_id=dropped.candidate.exercise_id,
                reason=f"Dropped the lowest-ranked {section} entry to fit the window.",
                used=(dropped.candidate.exercise_id,),
                score=dropped.ranking.score,
            )
        )


def _reduce_main_sets_until_fit(
    packed_by_section: dict[Section, list[_PackedEntry]],
    window: int,
    events: list[TraceEvent],
) -> None:
    main_entries = packed_by_section["main"]
    for index, packed_entry in reversed(tuple(enumerate(main_entries))):
        if _packed_minutes(packed_by_section) <= window + TIME_COMPARISON_TOLERANCE:
            return
        if (
            packed_entry.entry.reps is None
            or packed_entry.entry.sets <= MAIN_REDUCED_SETS
        ):
            continue
        reduced_entry = _entry(
            packed_entry.candidate,
            "main",
            sets_override=MAIN_REDUCED_SETS,
        )
        main_entries[index] = replace(packed_entry, entry=reduced_entry)
        events.append(
            PackingTraceEvent(
                action="cut",
                section="main",
                exercise_id=packed_entry.candidate.exercise_id,
                reason=f"Reduced main sets from {MAIN_SETS} to {MAIN_REDUCED_SETS}.",
                used=(packed_entry.candidate.exercise_id,),
                score=packed_entry.ranking.score,
            )
        )


def _packed_minutes(packed_by_section: dict[Section, list[_PackedEntry]]) -> float:
    return _round_minutes(
        sum(
            packed_entry.entry.minutes
            for entries in packed_by_section.values()
            for packed_entry in entries
        )
    )


def _plan_section(section: Section, packed_entries: list[_PackedEntry]) -> PlanSection:
    entries = tuple(packed_entry.entry for packed_entry in packed_entries)
    return PlanSection(
        section=section,
        entries=entries,
        minutes=_round_minutes(sum(entry.minutes for entry in entries)),
    )


def _round_minutes(minutes: float) -> float:
    return round(minutes, TIME_DECIMAL_PLACES)
