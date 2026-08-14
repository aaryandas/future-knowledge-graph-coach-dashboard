from app.generation._model import CatalogExercise, Plan, PlanEntry
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
    before_entries = _entries(before)
    after_entries = _entries(after)
    before_ids = frozenset(entry.exercise_id for entry in before_entries)
    after_ids = frozenset(entry.exercise_id for entry in after_entries)
    dropped = tuple(
        entry for entry in before_entries if entry.exercise_id not in after_ids
    )
    replacements = [
        entry for entry in after_entries if entry.exercise_id not in before_ids
    ]
    events: list[SubstitutionTraceEvent] = []

    for dropped_entry in dropped:
        if not replacements:
            break
        replacement_entry = min(
            replacements,
            key=lambda replacement: _pairing_key(
                catalog_by_id[dropped_entry.exercise_id],
                catalog_by_id[replacement.exercise_id],
            ),
        )
        if not _has_graph_overlap(
            catalog_by_id[dropped_entry.exercise_id],
            catalog_by_id[replacement_entry.exercise_id],
        ):
            continue
        replacements.remove(replacement_entry)
        events.append(
            _substitution_event(
                catalog_by_id[dropped_entry.exercise_id],
                catalog_by_id[replacement_entry.exercise_id],
            )
        )
    return tuple(events)


def _entries(plan: Plan) -> tuple[PlanEntry, ...]:
    return tuple(
        entry
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


def _has_graph_overlap(
    dropped: CatalogExercise,
    replacement: CatalogExercise,
) -> bool:
    return bool(
        _shared(dropped.movement_pattern_ids, replacement.movement_pattern_ids)
        or _shared(dropped.muscle_group_ids, replacement.muscle_group_ids)
    )


def _shared(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(frozenset(left).intersection(right)))
