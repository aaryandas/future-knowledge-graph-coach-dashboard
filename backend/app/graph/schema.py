from typing import Literal

type NodeLabel = Literal[
    "Exercise",
    "MuscleGroup",
    "Joint",
    "MovementPattern",
    "Equipment",
    "Injury",
    "AnatomicalStructure",
    "ClinicalFinding",
]
type EdgeType = Literal[
    "targets",
    "loads",
    "performs",
    "requires",
    "findingSite",
    "isA",
    "exactMatch",
    "contraindicates",
]
type TaxonomyField = tuple[str, NodeLabel, EdgeType, str]

NODE_LABELS: tuple[NodeLabel, ...] = (
    "Exercise",
    "MuscleGroup",
    "Joint",
    "MovementPattern",
    "Equipment",
    "Injury",
    "AnatomicalStructure",
    "ClinicalFinding",
)

EDGE_TYPES: tuple[EdgeType, ...] = (
    "targets",
    "loads",
    "performs",
    "requires",
    "findingSite",
    "isA",
    "exactMatch",
    "contraindicates",
)

EXERCISE_TAXONOMIES: tuple[TaxonomyField, ...] = (
    ("muscle_groups", "MuscleGroup", "targets", "muscle-group"),
    ("joints_loaded", "Joint", "loads", "joint"),
    ("movement_patterns", "MovementPattern", "performs", "movement-pattern"),
    ("equipment_required", "Equipment", "requires", "equipment"),
)
