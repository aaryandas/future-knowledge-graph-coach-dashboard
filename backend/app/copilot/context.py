from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.graph import get_member_context

type CopilotToneFactLabel = Literal["Journey stage", "Churn risk"]

COPILOT_TONE_FACT_LABELS: tuple[CopilotToneFactLabel, ...] = (
    "Journey stage",
    "Churn risk",
)


@dataclass(frozen=True)
class CopilotToneFact:
    label: CopilotToneFactLabel
    value: str
    evidence_node_ids: tuple[str, ...]


def get_copilot_tone_facts(
    member_id: str, *, as_of: date | None = None
) -> tuple[CopilotToneFact, ...]:
    """Return the two labeled facts that guide the future copilot's tone."""
    member_context = get_member_context(member_id, as_of=as_of)
    if member_context is None:
        return ()

    journey_evidence = member_context.journey_stage.evidence
    journey_node_ids = _node_ids(
        (journey_evidence.member_node_id,),
        journey_evidence.injury_node_ids,
        journey_evidence.workout_session_node_ids,
    )
    churn_node_ids = _node_ids(
        (member_context.profile.node_id,),
        (barrier.node_id for barrier in member_context.morning_brief.barriers),
        (
            evidence_node_id
            for barrier in member_context.morning_brief.barriers
            for evidence_node_id in barrier.evidence_node_ids
        ),
    )
    return (
        CopilotToneFact(
            label="Journey stage",
            value=member_context.journey_stage.stage,
            evidence_node_ids=journey_node_ids,
        ),
        CopilotToneFact(
            label="Churn risk",
            value=member_context.morning_brief.churn_risk_level,
            evidence_node_ids=churn_node_ids,
        ),
    )


def _node_ids(*node_id_groups: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(node_id for group in node_id_groups for node_id in group)
    )
