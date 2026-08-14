from typing import Literal

type NodeLabel = Literal[
    "Exercise",
    "MuscleGroup",
    "Joint",
    "MovementPattern",
    "Equipment",
    "AnatomicalStructure",
    "ClinicalFinding",
    "Member",
    "Goal",
    "MemberInjury",
    "WorkoutSession",
    "Observation",
    "ChatMessage",
    "Barrier",
    "CoachTask",
]
type EdgeType = Literal[
    "targets",
    "loads",
    "performs",
    "requires",
    "findingSite",
    "isA",
    "exactMatch",
    "pursues",
    "has",
    "owns",
    "performed",
    "observed",
    "said",
    "received",
    "dislikes",
    "included",
    "evidencedBy",
    "addresses",
]
type TaxonomyField = tuple[str, NodeLabel, EdgeType, str]

KG1_NODE_LABELS: tuple[NodeLabel, ...] = (
    "Exercise",
    "MuscleGroup",
    "Joint",
    "MovementPattern",
    "Equipment",
    "AnatomicalStructure",
    "ClinicalFinding",
)

KG2_NODE_LABELS: tuple[NodeLabel, ...] = (
    "Member",
    "Goal",
    "MemberInjury",
    "WorkoutSession",
    "Observation",
    "ChatMessage",
    "Barrier",
    "CoachTask",
)

NODE_LABELS: tuple[NodeLabel, ...] = (*KG1_NODE_LABELS, *KG2_NODE_LABELS)

KG1_EDGE_TYPES: tuple[EdgeType, ...] = (
    "targets",
    "loads",
    "performs",
    "requires",
    "findingSite",
    "isA",
    "exactMatch",
)

KG2_EDGE_TYPES: tuple[EdgeType, ...] = (
    "pursues",
    "has",
    "owns",
    "performed",
    "observed",
    "said",
    "received",
    "dislikes",
    "included",
    "exactMatch",
    "evidencedBy",
    "addresses",
)

EDGE_TYPES: tuple[EdgeType, ...] = tuple(
    dict.fromkeys((*KG1_EDGE_TYPES, *KG2_EDGE_TYPES))
)

EXERCISE_TAXONOMIES: tuple[TaxonomyField, ...] = (
    ("muscle_groups", "MuscleGroup", "targets", "muscle-group"),
    ("joints_loaded", "Joint", "loads", "joint"),
    ("movement_patterns", "MovementPattern", "performs", "movement-pattern"),
    ("equipment_required", "Equipment", "requires", "equipment"),
)
