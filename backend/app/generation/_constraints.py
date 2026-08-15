from app.generation._model import ConstraintSet, ResolvedIntent, ResolvedMention
from app.generation.intent import Intent


def merge_intent(current: Intent | None, delta: Intent) -> Intent:
    if current is None:
        return delta
    return Intent(
        focus=delta.focus if delta.focus is not None else current.focus,
        targets=_merge_raw_mentions(current.targets, delta.targets),
        exclusions=_merge_raw_mentions(current.exclusions, delta.exclusions),
        injuries=_merge_raw_mentions(current.injuries, delta.injuries),
        equipment=delta.equipment if delta.equipment else current.equipment,
    )


def merge_resolved_intent(
    current: ResolvedIntent | None,
    delta: ResolvedIntent,
) -> ResolvedIntent:
    if current is None:
        return delta
    return ResolvedIntent(
        targets=_merge_resolved_mentions(current.targets, delta.targets),
        constraints=merge_constraint_set(current.constraints, delta.constraints),
    )


def merge_constraint_set(current: ConstraintSet, delta: ConstraintSet) -> ConstraintSet:
    return ConstraintSet(
        exclusions=_merge_resolved_mentions(current.exclusions, delta.exclusions),
        session_injuries=_merge_resolved_mentions(
            current.session_injuries,
            delta.session_injuries,
        ),
        equipment_override=(
            delta.equipment_override
            if delta.equipment_override is not None
            else current.equipment_override
        ),
    )


def _merge_raw_mentions(
    current: tuple[str, ...], delta: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*current, *delta)))


def _merge_resolved_mentions(
    current: tuple[ResolvedMention, ...],
    delta: tuple[ResolvedMention, ...],
) -> tuple[ResolvedMention, ...]:
    merged: dict[tuple[str, str], ResolvedMention] = {
        _mention_key(mention): mention for mention in current
    }
    for mention in delta:
        merged[_mention_key(mention)] = mention
    return tuple(merged.values())


def _mention_key(mention: ResolvedMention) -> tuple[str, str]:
    resolution = mention.resolution
    return (
        mention.purpose,
        resolution.concept_id or resolution.raw_text.casefold().strip(),
    )
