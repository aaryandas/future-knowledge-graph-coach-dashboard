from typing import cast

from app.graph.store import neo4j_session


def get_exercise_movement_pattern_ids(exercise_id: str) -> frozenset[str]:
    with neo4j_session() as session:
        record = session.run(
            "MATCH (exercise:Exercise {id: $exercise_id}) "
            "OPTIONAL MATCH (exercise)-[:performs]->(pattern:MovementPattern) "
            "RETURN collect(pattern.id) AS movement_pattern_ids",
            exercise_id=exercise_id,
        ).single(strict=True)
    return frozenset(cast(list[str], record["movement_pattern_ids"]))
