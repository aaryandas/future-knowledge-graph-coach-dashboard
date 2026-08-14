from app.generation._model import CatalogExercise, Plan, PlanEntry, Section
from app.generation._trace import SubstitutionTraceEvent


def pair_substitutions(
    before: Plan | None,
    after: Plan,
    catalog: tuple[CatalogExercise, ...],
) -> tuple[SubstitutionTraceEvent, ...]:
    """Pair plan changes without changing which exercises the packer selected."""
    if before is None:
        return ()

    catalog_by_id = {exercise.exercise_id: exercise for exercise in catalog}
    before_entries = _section_entries(before)
    after_entries = _section_entries(after)
    before_ids = frozenset(entry.exercise_id for _, entry in before_entries)
    after_ids = frozenset(entry.exercise_id for _, entry in after_entries)
    dropped = tuple(
        (section, entry)
        for section, entry in before_entries
        if entry.exercise_id not in after_ids
    )
    replacements = [
        (section, entry)
        for section, entry in after_entries
        if entry.exercise_id not in before_ids
    ]
    events: list[SubstitutionTraceEvent] = []

    for dropped_section, dropped_entry in dropped:
        same_section = tuple(
            replacement
            for replacement in replacements
            if replacement[0] == dropped_section
        )
        available = same_section or tuple(replacements)
        if not available:
            break
        replacement_section, replacement_entry = min(
            available,
            key=lambda replacement: _pairing_key(
                catalog_by_id[dropped_entry.exercise_id],
                catalog_by_id[replacement[1].exercise_id],
            ),
        )
        replacements.remove((replacement_section, replacement_entry))
        events.append(
            _substitution_event(
                catalog_by_id[dropped_entry.exercise_id],
                catalog_by_id[replacement_entry.exercise_id],
            )
        )
    return tuple(events)


def _section_entries(plan: Plan) -> tuple[tuple[Section, PlanEntry], ...]:
    return tuple(
        (section.section, entry)
        for section in (plan.warm_up, plan.main, plan.cool_down)
        for entry in section.entries
    )


def _pairing_key(
    dropped: CatalogExercise,
    replacement: CatalogExercise,
) -> tuple[int, int, int, str, str]:
    shared_patterns = _shared(
        dropped.movement_pattern_ids,
        replacement.movement_pattern_ids,
    )
    shared_muscles = _shared(
        dropped.muscle_group_ids,
        replacement.muscle_group_ids,
    )
    return (
        -int(bool(shared_patterns)),
        -len(shared_patterns),
        -len(shared_muscles),
        replacement.name,
        replacement.exercise_id,
    )


def _substitution_event(
    dropped: CatalogExercise,
    replacement: CatalogExercise,
) -> SubstitutionTraceEvent:
    shared_patterns = _shared(
        dropped.movement_pattern_ids,
        replacement.movement_pattern_ids,
    )
    shared_muscles = _shared(
        dropped.muscle_group_ids,
        replacement.muscle_group_ids,
    )
    basis = "movement pattern" if shared_patterns else "muscle overlap"
    shared = shared_patterns if shared_patterns else shared_muscles
    reason = (
        f"Replaced {dropped.name} with {replacement.name} by shared {basis}: "
        f"{', '.join(shared) if shared else 'none'}."
    )
    return SubstitutionTraceEvent(
        dropped_exercise_id=dropped.exercise_id,
        replacement_exercise_id=replacement.exercise_id,
        basis=basis,
        shared_movement_pattern_ids=shared_patterns,
        shared_muscle_group_ids=shared_muscles,
        reason=reason,
        used=(dropped.exercise_id, replacement.exercise_id, *shared),
    )


def _shared(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(frozenset(left).intersection(right)))
