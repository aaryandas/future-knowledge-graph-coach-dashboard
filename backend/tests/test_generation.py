from app.api.generation_parts import generation_data_parts
from app.generation.testing import (
    CatalogExercise,
    FakeLLM,
    GenerationMemberContext,
    ResolvedMention,
    Verdict,
    WalkedPath,
    run_checkpointed_session,
)
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "mbr_01HX9JORDAN"


def test_adjustment_merges_checkpointed_constraint_set_and_pairs_substitution() -> None:
    llm = FakeLLM(
        [
            {
                "focus": "lower-body",
                "targets": [],
                "exclusions": [],
                "injuries": [],
                "equipment": [],
            },
            {
                "focus": None,
                "targets": [],
                "exclusions": ["Dumbbell Goblet Split Squat"],
                "injuries": ["knee"],
                "equipment": ["Dumbbell"],
            },
            {
                "focus": None,
                "targets": [],
                "exclusions": ["moon burpees"],
                "injuries": ["quantum knee"],
                "equipment": [],
            },
        ]
    )
    checkpointer = InMemorySaver()
    received_session_injuries: list[tuple[ResolvedMention, ...]] = []

    def verdict_evaluator(
        member_id: str,
        exercise_ids: tuple[str, ...],
        session_injuries: tuple[ResolvedMention, ...],
    ) -> tuple[Verdict, ...]:
        assert member_id == MEMBER_ID
        received_session_injuries.append(session_injuries)
        return tuple(
            Verdict(
                exercise_id=exercise_id,
                status="clear",
                walked_path=WalkedPath(nodes=(), edges=()),
                decisions=(),
                trace=(),
            )
            for exercise_id in exercise_ids
        )

    first = run_checkpointed_session(
        MEMBER_ID,
        "Build a lower-body workout.",
        20,
        "thread-1",
        checkpointer=checkpointer,
        llm=llm,
        catalog_reader=_catalog,
        member_context_reader=_member_context,
        verdict_evaluator=verdict_evaluator,
    )
    second = run_checkpointed_session(
        MEMBER_ID,
        "Exclude the split squat; her knee hurts; dumbbells only.",
        20,
        "thread-1",
        checkpointer=checkpointer,
        llm=llm,
        catalog_reader=_catalog,
        member_context_reader=_member_context,
        verdict_evaluator=verdict_evaluator,
    )
    third = run_checkpointed_session(
        MEMBER_ID,
        "Also avoid moon burpees; her quantum knee hurts.",
        20,
        "thread-1",
        checkpointer=checkpointer,
        llm=llm,
        catalog_reader=_catalog,
        member_context_reader=_member_context,
        verdict_evaluator=verdict_evaluator,
    )

    assert first.plan is not None
    assert second.plan is not None
    assert first.plan.main.entries[0].name == "Dumbbell Goblet Split Squat"
    assert second.plan.main.entries[0].name == "Kettlebell Goblet Cyclist Squat"
    assert second.resolved_intent is not None
    assert [
        mention.resolution.raw_text
        for mention in second.resolved_intent.constraints.exclusions
    ] == ["Dumbbell Goblet Split Squat"]
    assert [
        mention.resolution.raw_text
        for mention in second.resolved_intent.constraints.session_injuries
    ] == ["knee"]
    assert second.resolved_intent.constraints.equipment_override is not None
    assert (
        second.resolved_intent.constraints.equipment_override[0].resolution.raw_text
        == "Dumbbell"
    )
    assert received_session_injuries[0] == ()
    assert received_session_injuries[1][0].enforced is True

    second_parts = [
        part.model_dump(mode="json", by_alias=True)
        for part in generation_data_parts(second)
    ]
    assert [(part["type"], part["id"]) for part in second_parts] == [
        ("data-plan", "generation-plan"),
        ("data-trace", "generation-trace"),
        ("data-constraints", "generation-constraints"),
    ]
    substitution = next(
        event for event in second_parts[1]["data"] if event["kind"] == "substitution"
    )
    assert substitution["dropped_exercise_id"] == _MAIN_DUMBBELL_ID
    assert substitution["replacement_exercise_id"] == _MAIN_KETTLEBELL_ID
    assert substitution["basis"] == "muscle overlap"

    third_parts = generation_data_parts(third)
    constraints = third_parts[2].model_dump(mode="json")["data"]
    assert [chip["raw_text"] for chip in constraints["omissions"]] == ["moon burpees"]
    assert [flag["raw_text"] for flag in constraints["not_enforced"]] == [
        "quantum knee"
    ]
    assert [
        suggestion["raw_text"]
        for suggestion in constraints["session_injury_persistence_suggestions"]
    ] == ["knee"]
    assert (
        constraints["session_injury_persistence_suggestions"][0][
            "requires_confirmation"
        ]
        is True
    )


_MAIN_DUMBBELL_ID = "02fe4cf5-bb21-4bef-868f-fea1477e2a53"
_MAIN_KETTLEBELL_ID = "00036a08-7c22-42e4-8fe5-323b53e31667"


def _catalog() -> tuple[CatalogExercise, ...]:
    return (
        _exercise(
            exercise_id="0a4d99cf-5075-468e-9551-b9f8efa267f1",
            name="World's Greatest Stretch",
            pattern="mobility - dynamic",
            muscles=("hamstrings",),
            is_reps=True,
            rep_duration=0.05,
        ),
        _exercise(
            exercise_id=_MAIN_DUMBBELL_ID,
            name="Dumbbell Goblet Split Squat",
            pattern="lower push - split squat",
            muscles=("quads", "glutes"),
            is_reps=True,
            rep_duration=0.5,
        ),
        _exercise(
            exercise_id=_MAIN_KETTLEBELL_ID,
            name="Kettlebell Goblet Cyclist Squat",
            pattern="lower push - squat",
            muscles=("quads", "glutes"),
            is_reps=True,
            rep_duration=0.5,
        ),
        _exercise(
            exercise_id="1965072a-7e34-4d37-98f5-bde8cb6629a4",
            name="Cow Pose",
            pattern="mobility - static",
            muscles=("lower back",),
            is_reps=False,
            rep_duration=0.0,
        ),
    )


def _member_context(_member_id: str) -> GenerationMemberContext:
    return GenerationMemberContext(
        equipment_ids=(),
        disliked_exercise_ids=(),
    )


def _exercise(
    *,
    exercise_id: str,
    name: str,
    pattern: str,
    muscles: tuple[str, ...],
    is_reps: bool,
    rep_duration: float,
) -> CatalogExercise:
    pattern_id = f"fkg:movement-pattern/{pattern.replace(' ', '-')}"
    return CatalogExercise(
        exercise_id=exercise_id,
        name=name,
        movement_patterns=(pattern,),
        movement_pattern_ids=(pattern_id,),
        muscle_groups=muscles,
        muscle_group_ids=tuple(
            f"fkg:muscle-group/{muscle.replace(' ', '-')}" for muscle in muscles
        ),
        joint_ids=(),
        equipment_ids=(),
        priority_tier=2,
        is_reps=is_reps,
        is_duration=True,
        supports_weight=is_reps,
        estimated_rep_duration=rep_duration,
        is_bilateral=False,
        side=None,
        bilateral_pair_id=None,
    )
