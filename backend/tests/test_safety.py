from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal

import pytest
from app.graph import ingest_kg1, ingest_kg2
from app.safety import AgentDecision, evaluate_safety

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = REPOSITORY_ROOT / "data"
MEMBER_ID = "mbr_01HX9JORDAN"
STATIC_JUMP_ID = "01ff62bc-e887-49e4-9cc8-bcd367b34cfd"
CYCLIST_SQUAT_ID = "00036a08-7c22-42e4-8fe5-323b53e31667"
RNT_SPLIT_SQUAT_ID = "00cc383b-f156-4b23-952a-15340100c261"
PREACHER_CURL_ID = "004717c7-4e34-4a26-978f-50106f09abcc"


@pytest.fixture(scope="module", autouse=True)
def seeded_graph() -> None:
    ingest_kg1()
    ingest_kg2()


@pytest.mark.parametrize(
    ("exercise_id", "status", "layer", "node_kinds", "edge_kinds"),
    (
        (
            STATIC_JUMP_ID,
            "exclude",
            "clinical directive",
            ("MemberInjury", "MovementPattern", "Exercise"),
            ("performs",),
        ),
        (
            CYCLIST_SQUAT_ID,
            "caution",
            "contraindication",
            (
                "MemberInjury",
                "ClinicalFinding",
                "Injury",
                "MovementPattern",
                "Exercise",
            ),
            ("exactMatch", "exactMatch", "contraindicates", "performs"),
        ),
        (
            RNT_SPLIT_SQUAT_ID,
            "caution",
            "SNOMED anatomical fallback",
            (
                "MemberInjury",
                "ClinicalFinding",
                "AnatomicalStructure",
                "AnatomicalStructure",
                "AnatomicalStructure",
                "Joint",
                "Exercise",
            ),
            (
                "exactMatch",
                "findingSite",
                "isA",
                "isA",
                "exactMatch",
                "loads",
            ),
        ),
        (PREACHER_CURL_ID, "clear", None, ("Exercise",), ()),
    ),
)
def test_safety_layers_return_verdicts_with_walked_paths(
    exercise_id: str,
    status: str,
    layer: str | None,
    node_kinds: tuple[str, ...],
    edge_kinds: tuple[str, ...],
) -> None:
    (verdict,) = evaluate_safety(MEMBER_ID, (exercise_id,))

    assert verdict.exercise_id == exercise_id
    assert verdict.status == status
    assert verdict.decisions[0].kind == "graph"
    assert verdict.decisions[0].layer == layer
    assert tuple(node.kind for node in verdict.walked_path.nodes) == node_kinds
    assert tuple(edge.kind for edge in verdict.walked_path.edges) == edge_kinds


@pytest.mark.parametrize(
    ("status", "severity", "exercise_id", "expected"),
    (
        ("recovering", "mild", CYCLIST_SQUAT_ID, "caution"),
        ("active", "mild", CYCLIST_SQUAT_ID, "exclude"),
        ("recovering", "moderate", CYCLIST_SQUAT_ID, "exclude"),
        ("recovering", "severe", CYCLIST_SQUAT_ID, "exclude"),
        ("resolved", "severe", STATIC_JUMP_ID, "clear"),
    ),
)
def test_status_and_severity_only_escalate_verdicts(
    tmp_path: Path,
    status: str,
    severity: str,
    exercise_id: str,
    expected: str,
) -> None:
    data_directory = tmp_path / "data"
    shutil.copytree(DATA_DIRECTORY, data_directory)
    member_path = data_directory / "member-context.json"
    member = json.loads(member_path.read_text())
    member["injuries"][0].update(status=status, severity=severity)
    member_path.write_text(json.dumps(member))

    try:
        ingest_kg2(data_directory)
        (verdict,) = evaluate_safety(MEMBER_ID, (exercise_id,))
    finally:
        ingest_kg2()

    assert verdict.status == expected


@pytest.mark.parametrize(
    ("status", "severity"),
    (
        ("recovering", "mild"),
        ("active", "mild"),
        ("recovering", "moderate"),
        ("recovering", "severe"),
    ),
)
def test_authored_avoid_remains_excluded_across_escalation_matrix(
    tmp_path: Path,
    status: str,
    severity: str,
) -> None:
    data_directory = tmp_path / "data"
    shutil.copytree(DATA_DIRECTORY, data_directory)
    member_path = data_directory / "member-context.json"
    member = json.loads(member_path.read_text())
    member_id = f"mbr_authored_avoid_{status}_{severity}"
    member["profile"]["id"] = member_id
    member["injuries"][0].update(
        status=status,
        severity=severity,
        notes="No clinical directive.",
        finding="Sprain of lateral ligament of ankle joint",
        snomedct_hint="",
    )
    member_path.write_text(json.dumps(member))

    try:
        ingest_kg2(data_directory)
        (verdict,) = evaluate_safety(member_id, (STATIC_JUMP_ID,))
    finally:
        ingest_kg2()

    assert verdict.status == "exclude"
    decision = verdict.decisions[0]
    assert decision.kind == "graph"
    assert decision.layer == "contraindication"


@pytest.mark.parametrize(
    ("exercise_id", "agent_status", "expected_status", "expected_kinds"),
    (
        (PREACHER_CURL_ID, "caution", "caution", ("graph", "agent")),
        (CYCLIST_SQUAT_ID, "exclude", "exclude", ("graph", "agent")),
        (STATIC_JUMP_ID, "caution", "exclude", ("graph",)),
    ),
)
def test_agent_may_tighten_the_safety_floor_but_never_loosen_it(
    exercise_id: str,
    agent_status: Literal["exclude", "caution"],
    expected_status: str,
    expected_kinds: tuple[str, ...],
) -> None:
    decision = AgentDecision(
        exercise_id=exercise_id,
        status=agent_status,
        reason="Recent pain context",
    )

    (verdict,) = evaluate_safety(MEMBER_ID, (exercise_id,), agent_decisions=(decision,))

    assert verdict.status == expected_status
    assert tuple(item.kind for item in verdict.decisions) == expected_kinds


def test_resolver_parsed_clinical_clearance_has_highest_precedence(
    tmp_path: Path,
) -> None:
    data_directory = tmp_path / "data"
    shutil.copytree(DATA_DIRECTORY, data_directory)
    member_path = data_directory / "member-context.json"
    member = json.loads(member_path.read_text())
    member["injuries"][0]["notes"] = "Cleared for cardio - plyometric."
    member_path.write_text(json.dumps(member))

    try:
        ingest_kg2(data_directory)
        (verdict,) = evaluate_safety(MEMBER_ID, (STATIC_JUMP_ID,))
    finally:
        ingest_kg2()

    assert verdict.status == "clear"
    decision = verdict.decisions[0]
    assert decision.kind == "graph"
    assert decision.layer == "clinical directive"


def test_resolved_injury_stays_visible_without_softening_another_injury(
    tmp_path: Path,
) -> None:
    data_directory = tmp_path / "data"
    shutil.copytree(DATA_DIRECTORY, data_directory)
    member_path = data_directory / "member-context.json"
    member = json.loads(member_path.read_text())
    member["profile"]["id"] = "mbr_safety_provenance"
    resolved = member["injuries"][0]
    resolved.update(id="inj_resolved", status="resolved", severity="severe")
    recovering = {
        **resolved,
        "id": "inj_recovering",
        "status": "recovering",
        "severity": "mild",
        "notes": "No clinical directive.",
    }
    member["injuries"] = [resolved, recovering]
    member_path.write_text(json.dumps(member))

    ingest_kg2(data_directory)
    (verdict,) = evaluate_safety("mbr_safety_provenance", (STATIC_JUMP_ID,))

    graph_decisions = tuple(
        decision for decision in verdict.decisions if decision.kind == "graph"
    )
    assert verdict.status == "caution"
    assert {decision.injury_status for decision in graph_decisions} == {
        "recovering",
        "resolved",
    }
    assert verdict.walked_path == graph_decisions[0].walked_path
