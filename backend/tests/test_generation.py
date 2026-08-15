from app.generation import GenerationTurn, run_generation_session
from app.generation.testing import (
    CatalogExercise,
    FakeLLM,
    GenerationMemberContext,
    ResolvedMention,
    Verdict,
    WalkedPath,
    generation_test_adapters,
)

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
                "injuries": ["quantum flux"],
                "equipment": [],
            },
        ]
    )
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

    with generation_test_adapters(
        llm=llm,
        catalog_reader=_catalog,
        member_context_reader=_member_context,
        verdict_evaluator=verdict_evaluator,
    ):
        first, second, third = (
            run_generation_session(
                MEMBER_ID,
                message,
                20,
                "thread-1",
                f"message-{index}",
            )
            for index, message in enumerate(
                (
                    "Build a lower-body workout.",
                    "Exclude the split squat; her knee hurts; dumbbells only.",
                    "Also avoid moon burpees; she reports quantum flux.",
                ),
                start=1,
            )
        )
    turns: tuple[GenerationTurn, ...] = (first, second, third)

    first_plan = turns[0].plan
    second_plan = turns[1].plan
    second_intent = turns[1].resolved_intent
    third_intent = turns[2].resolved_intent
    assert first_plan is not None
    assert second_plan is not None
    assert second_intent is not None
    assert third_intent is not None
    assert first_plan.main.entries[0].name == "Dumbbell Goblet Split Squat"
    assert second_plan.main.entries[0].name == "Kettlebell Goblet Cyclist Squat"
    assert [
        mention.resolution.raw_text for mention in second_intent.constraints.exclusions
    ] == ["Dumbbell Goblet Split Squat"]
    assert [
        mention.resolution.raw_text
        for mention in second_intent.constraints.session_injuries
    ] == ["knee"]
    assert second_intent.constraints.equipment_override is not None
    assert (
        second_intent.constraints.equipment_override[0].resolution.raw_text
        == "Dumbbell"
    )
    assert received_session_injuries[0] == ()
    assert received_session_injuries[1][0].enforced is True

    substitution = next(
        event for event in turns[1].trace if event.kind == "substitution"
    )
    assert substitution.dropped_exercise_id == _MAIN_DUMBBELL_ID
    assert substitution.replacement_exercise_id == _MAIN_KETTLEBELL_ID
    assert substitution.basis == "muscle overlap"

    assert [
        mention.resolution.raw_text for mention in third_intent.constraints.exclusions
    ] == ["Dumbbell Goblet Split Squat", "moon burpees"]
    unresolved_exclusion = third_intent.constraints.exclusions[1]
    assert unresolved_exclusion.enforced is False
    assert unresolved_exclusion.resolution.candidates
    assert [
        mention.resolution.raw_text
        for mention in third_intent.constraints.session_injuries
    ] == ["knee", "quantum flux"]
    assert [
        mention.resolution.raw_text
        for mention in third_intent.constraints.session_injuries
        if not mention.enforced
    ] == ["quantum flux"]
    assert [
        mention.resolution.raw_text
        for mention in third_intent.constraints.session_injuries
        if mention.enforced
    ] == ["knee"]


def test_exact_named_adjustment_preserves_unaffected_plan_entries() -> None:
    llm = FakeLLM(
        [
            {
                "focus": None,
                "targets": [],
                "exclusions": [],
                "injuries": [],
                "equipment": [],
            },
            {
                "focus": None,
                "targets": [],
                "exclusions": ["Bodyweight Pike"],
                "injuries": [],
                "equipment": [],
            },
        ]
    )

    with generation_test_adapters(
        llm=llm,
        catalog_reader=_local_adjustment_catalog,
        member_context_reader=_member_context,
        verdict_evaluator=_clear_verdicts,
    ):
        initial = run_generation_session(
            MEMBER_ID,
            "Build a yoga-mat workout.",
            20,
            "thread-exact-removal",
            "message-1",
        )
        adjusted = run_generation_session(
            MEMBER_ID,
            "Remove Bodyweight Pike.",
            20,
            "thread-exact-removal",
            "message-2",
        )

    assert initial.plan is not None
    assert adjusted.plan is not None
    assert initial.plan.warm_up == adjusted.plan.warm_up
    assert initial.plan.cool_down == adjusted.plan.cool_down
    initial_plank = next(
        entry
        for entry in initial.plan.main.entries
        if entry.exercise_id == _LOW_PLANK_ID
    )
    assert any(
        entry.exercise_id == _BODYWEIGHT_PIKE_ID for entry in initial.plan.main.entries
    )
    assert initial_plank in adjusted.plan.main.entries
    assert all(
        entry.exercise_id != _BODYWEIGHT_PIKE_ID for entry in adjusted.plan.main.entries
    )

    substitution = next(
        event for event in adjusted.trace if event.kind == "substitution"
    )
    assert substitution.dropped_exercise_id == _BODYWEIGHT_PIKE_ID
    assert substitution.replacement_exercise_id == _HIGH_PLANK_BIRD_DOG_ID


def test_natural_movement_pattern_adjustment_excludes_matching_exercises() -> None:
    llm = FakeLLM(
        [
            {
                "focus": None,
                "targets": [],
                "exclusions": [],
                "injuries": [],
                "equipment": [],
            },
            {
                "focus": None,
                "targets": [],
                "exclusions": ["deadlifts"],
                "injuries": [],
                "equipment": [],
            },
        ]
    )

    with generation_test_adapters(
        llm=llm,
        catalog_reader=_movement_pattern_adjustment_catalog,
        member_context_reader=_member_context,
        verdict_evaluator=_clear_verdicts,
    ):
        initial = run_generation_session(
            MEMBER_ID,
            "Build a lower-body workout.",
            20,
            "thread-movement-pattern-removal",
            "message-1",
        )
        adjusted = run_generation_session(
            MEMBER_ID,
            "Remove deadlifts.",
            20,
            "thread-movement-pattern-removal",
            "message-2",
        )

    assert initial.plan is not None
    assert adjusted.plan is not None
    assert {entry.exercise_id for entry in initial.plan.main.entries}.issuperset(
        _DEADLIFT_IDS
    )
    assert {entry.exercise_id for entry in adjusted.plan.main.entries}.isdisjoint(
        _DEADLIFT_IDS
    )
    assert adjusted.resolved_intent is not None
    exclusion = adjusted.resolved_intent.constraints.exclusions[0]
    assert exclusion.vocabulary == "Exercise"
    assert exclusion.resolution.concept_id == _BARBELL_DEADLIFT_ID
    assert exclusion.resolution.pass_ == "fuzzy"
    assert {
        candidate.concept_id for candidate in exclusion.resolution.candidates
    }.issuperset({_DUMBBELL_ROMANIAN_DEADLIFT_ID, _KETTLEBELL_ROMANIAN_DEADLIFT_ID})
    assert exclusion.derived_exclusion_rule is not None
    assert exclusion.derived_exclusion_rule.vocabulary == "MovementPattern"
    assert exclusion.derived_exclusion_rule.concept_id == _HIP_HINGE_MOVEMENT_PATTERN_ID


def test_failed_adjustment_does_not_emit_previous_incompatible_plan() -> None:
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
                "exclusions": [],
                "injuries": ["knee"],
                "equipment": [],
            },
        ]
    )

    def exclude_warm_up_after_injury(
        member_id: str,
        exercise_ids: tuple[str, ...],
        session_injuries: tuple[ResolvedMention, ...],
    ) -> tuple[Verdict, ...]:
        assert member_id == MEMBER_ID
        return tuple(
            Verdict(
                exercise_id=exercise_id,
                status=(
                    "exclude"
                    if session_injuries
                    and exercise_id == "0a4d99cf-5075-468e-9551-b9f8efa267f1"
                    else "clear"
                ),
                walked_path=WalkedPath(nodes=(), edges=()),
                decisions=(),
                trace=(),
            )
            for exercise_id in exercise_ids
        )

    with generation_test_adapters(
        llm=llm,
        catalog_reader=_catalog,
        member_context_reader=_member_context,
        verdict_evaluator=exclude_warm_up_after_injury,
    ):
        initial = run_generation_session(
            MEMBER_ID,
            "Build a lower-body workout.",
            20,
            "thread-packing-failure",
            "message-1",
        )
        adjusted = run_generation_session(
            MEMBER_ID,
            "Her left knee is bothering her today.",
            20,
            "thread-packing-failure",
            "message-2",
        )

    assert initial.plan is not None
    assert adjusted.failure is not None
    assert adjusted.failure.reason == "empty-section"
    assert adjusted.plan is None


_MAIN_DUMBBELL_ID = "02fe4cf5-bb21-4bef-868f-fea1477e2a53"
_MAIN_KETTLEBELL_ID = "00036a08-7c22-42e4-8fe5-323b53e31667"
_BODYWEIGHT_PIKE_ID = "0a2dc786-fb42-4571-9b26-f58cdeb2c70e"
_LOW_PLANK_ID = "00e18a26-70dd-4d43-b013-5038b75a41f3"
_HIGH_PLANK_BIRD_DOG_ID = "01f5a2bb-ecf7-4168-92b3-35bd78592e26"
_BARBELL_DEADLIFT_ID = "2f787955-4e40-4103-9d9e-7f0d22b3e194"
_DUMBBELL_ROMANIAN_DEADLIFT_ID = "9b09c2e8-d997-4b9b-b13b-986ade901fc7"
_KETTLEBELL_ROMANIAN_DEADLIFT_ID = "90900327-80eb-4981-9a09-c218484be28b"
_DEADLIFT_IDS = {
    _BARBELL_DEADLIFT_ID,
    _DUMBBELL_ROMANIAN_DEADLIFT_ID,
    _KETTLEBELL_ROMANIAN_DEADLIFT_ID,
}
_HIP_HINGE_MOVEMENT_PATTERN_ID = "fkg:movement-pattern/lower-pull-hip-hinge"


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


def _local_adjustment_catalog() -> tuple[CatalogExercise, ...]:
    warm_up, _, _, cool_down = _catalog()
    return (
        warm_up,
        _exercise(
            exercise_id=_LOW_PLANK_ID,
            name="Alternating Low Plank To Low Side Plank",
            patterns=("core - anti-lateral flexion", "core - anti-extension"),
            muscles=("core", "obliques", "deltoids"),
            is_reps=True,
            rep_duration=0.1,
        ),
        _exercise(
            exercise_id=_BODYWEIGHT_PIKE_ID,
            name="Bodyweight Pike",
            patterns=("core - flexion", "core - anti-extension"),
            muscles=("deltoids", "core", "hip flexors"),
            is_reps=True,
            rep_duration=0.3,
        ),
        _exercise(
            exercise_id=_HIGH_PLANK_BIRD_DOG_ID,
            name="High Plank Bird Dog",
            patterns=("core - anti-rotation", "isometric", "quadruped"),
            muscles=("core", "deltoids"),
            is_reps=True,
            rep_duration=0.2,
            priority_tier=3,
        ),
        cool_down,
    )


def _movement_pattern_adjustment_catalog() -> tuple[CatalogExercise, ...]:
    warm_up, _, replacement, cool_down = _catalog()
    return (
        warm_up,
        _exercise(
            exercise_id=_BARBELL_DEADLIFT_ID,
            name="Barbell Deadlift",
            pattern="lower pull - hip hinge",
            muscles=("glutes", "hamstrings", "quads", "lower back"),
            is_reps=True,
            rep_duration=0.1,
        ),
        _exercise(
            exercise_id=_DUMBBELL_ROMANIAN_DEADLIFT_ID,
            name="Dumbbell Romanian Deadlift",
            pattern="lower pull - hip hinge",
            muscles=("hamstrings", "glutes", "lower back"),
            is_reps=True,
            rep_duration=0.1,
        ),
        _exercise(
            exercise_id=_KETTLEBELL_ROMANIAN_DEADLIFT_ID,
            name="Kettlebell Romanian Deadlift",
            pattern="lower pull - hip hinge",
            muscles=("hamstrings", "glutes", "lower back"),
            is_reps=True,
            rep_duration=0.1,
        ),
        replacement,
        cool_down,
    )


def _clear_verdicts(
    _member_id: str,
    exercise_ids: tuple[str, ...],
    _session_injuries: tuple[ResolvedMention, ...],
) -> tuple[Verdict, ...]:
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


def _member_context(_member_id: str) -> GenerationMemberContext:
    return GenerationMemberContext(
        equipment_ids=(),
        disliked_exercise_ids=(),
    )


def _exercise(
    *,
    exercise_id: str,
    name: str,
    pattern: str | None = None,
    patterns: tuple[str, ...] | None = None,
    muscles: tuple[str, ...],
    is_reps: bool,
    rep_duration: float,
    priority_tier: int = 2,
) -> CatalogExercise:
    movement_patterns = patterns or ((pattern,) if pattern is not None else ())
    return CatalogExercise(
        exercise_id=exercise_id,
        name=name,
        movement_patterns=movement_patterns,
        movement_pattern_ids=tuple(
            f"fkg:movement-pattern/{value.replace(' - ', '-').replace(' ', '-')}"
            for value in movement_patterns
        ),
        muscle_groups=muscles,
        muscle_group_ids=tuple(
            f"fkg:muscle-group/{muscle.replace(' ', '-')}" for muscle in muscles
        ),
        joint_ids=(),
        equipment_ids=(),
        priority_tier=priority_tier,
        is_reps=is_reps,
        is_duration=True,
        supports_weight=is_reps,
        estimated_rep_duration=rep_duration,
        is_bilateral=False,
        side=None,
        bilateral_pair_id=None,
    )
