from app.generation._model import ResolvedMention
from app.safety import SessionInjury, Verdict, evaluate_safety


def evaluate_generation_safety(
    member_id: str,
    exercise_ids: tuple[str, ...],
    session_injuries: tuple[ResolvedMention, ...],
) -> tuple[Verdict, ...]:
    return evaluate_safety(
        member_id,
        exercise_ids,
        session_injuries=tuple(
            safety_injury
            for mention in session_injuries
            if (safety_injury := _session_injury(mention)) is not None
        ),
    )


def _session_injury(mention: ResolvedMention) -> SessionInjury | None:
    concept_id = mention.resolution.concept_id
    if (
        not mention.enforced
        or concept_id is None
        or mention.vocabulary not in {"Joint", "AnatomicalStructure", "ClinicalFinding"}
    ):
        return None
    return SessionInjury(concept_id=concept_id, kind=mention.vocabulary)
