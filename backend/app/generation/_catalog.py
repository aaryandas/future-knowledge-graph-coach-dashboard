from __future__ import annotations

from typing import Any, cast

from neo4j import Record

from app.generation._model import CatalogExercise, GenerationMemberContext
from app.graph import get_member_profile
from app.graph.store import neo4j_session


def read_catalog_exercises() -> tuple[CatalogExercise, ...]:
    with neo4j_session() as session:
        records = session.run(
            "MATCH (exercise:Exercise) "
            "OPTIONAL MATCH (exercise)-[taxonomy:targets|loads|performs|requires]"
            "->(concept) "
            "RETURN exercise.id AS exercise_id, exercise.name AS sort_name, "
            "properties(exercise) AS properties, "
            "collect({kind: type(taxonomy), id: concept.id, name: concept.name}) "
            "AS taxonomy "
            "ORDER BY sort_name, exercise_id"
        )
        return tuple(_catalog_exercise(record) for record in records)


def read_generation_member_context(
    member_id: str,
) -> GenerationMemberContext | None:
    profile = get_member_profile(member_id)
    if profile is None:
        return None
    return GenerationMemberContext(
        equipment_ids=profile.equipment_node_ids,
        disliked_exercise_ids=profile.exercise_node_ids,
    )


def _catalog_exercise(record: Record) -> CatalogExercise:
    properties = cast(dict[str, Any], record["properties"])
    taxonomy = cast(list[dict[str, object]], record["taxonomy"])
    return CatalogExercise(
        exercise_id=cast(str, record["exercise_id"]),
        name=_string(properties, "name"),
        movement_patterns=_taxonomy_values(taxonomy, "performs", "name"),
        movement_pattern_ids=_taxonomy_values(taxonomy, "performs", "id"),
        muscle_groups=_taxonomy_values(taxonomy, "targets", "name"),
        muscle_group_ids=_taxonomy_values(taxonomy, "targets", "id"),
        joint_ids=_taxonomy_values(taxonomy, "loads", "id"),
        equipment_ids=_taxonomy_values(taxonomy, "requires", "id"),
        priority_tier=_int(properties, "priority_tier"),
        is_reps=_bool(properties, "is_reps"),
        is_duration=_bool(properties, "is_duration"),
        supports_weight=_bool(properties, "supports_weight"),
        estimated_rep_duration=_number(properties, "estimated_rep_duration"),
        is_bilateral=_bool(properties, "is_bilateral"),
        side=_optional_string(properties, "side"),
        bilateral_pair_id=_optional_string(properties, "bilateral_pair_id"),
    )


def _taxonomy_values(
    taxonomy: list[dict[str, object]], kind: str, field: str
) -> tuple[str, ...]:
    return tuple(
        sorted(
            cast(str, item[field])
            for item in taxonomy
            if item.get("kind") == kind and isinstance(item.get(field), str)
        )
    )


def _string(properties: dict[str, Any], key: str) -> str:
    value = properties.get(key)
    if not isinstance(value, str):
        raise TypeError(f"Exercise property {key} is not a string")
    return value


def _optional_string(properties: dict[str, Any], key: str) -> str | None:
    value = properties.get(key)
    if value is not None and not isinstance(value, str):
        raise RuntimeError(f"Exercise property {key} is not a string or null")
    return value


def _bool(properties: dict[str, Any], key: str) -> bool:
    value = properties.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Exercise property {key} is not a boolean")
    return value


def _int(properties: dict[str, Any], key: str) -> int:
    value = properties.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Exercise property {key} is not an integer")
    return value


def _number(properties: dict[str, Any], key: str) -> float:
    value = properties.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"Exercise property {key} is not a number")
    return float(value)
