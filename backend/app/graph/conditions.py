import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

CONDITIONS_SOURCE = "data/conditions.json"

type JsonObject = dict[str, Any]
type ContraindicationTarget = Literal["MovementPattern", "Joint"]
type AuthoredVerdict = Literal["exclude", "caution"]


@dataclass(frozen=True)
class ConditionRow:
    injury_id: str
    name: str
    clinical_finding_id: str
    target_kind: ContraindicationTarget
    target_id: str
    verdict: AuthoredVerdict
    note: str
    citation: str
    citation_url: str


@dataclass(frozen=True)
class AuthoredConditions:
    rows: tuple[ConditionRow, ...]
    version: str


def load_conditions(path: Path) -> AuthoredConditions:
    source_bytes = path.read_bytes()
    value = json.loads(source_bytes)
    if not isinstance(value, list):
        raise TypeError(f"{path} must contain a JSON array")

    rows = tuple(_condition_row(item, index) for index, item in enumerate(value))
    pairs = [(row.injury_id, row.target_id) for row in rows]
    if len(pairs) != len(set(pairs)):
        raise ValueError(f"{path} contains duplicate condition-target rows")

    return AuthoredConditions(rows=rows, version=sha256(source_bytes).hexdigest())


def _condition_row(value: Any, index: int) -> ConditionRow:
    row = _object(value, f"Condition row {index}")
    injury_id = _required_string(row, "id", index)
    if not injury_id.startswith("fkg:injury/"):
        raise ValueError(f"Condition row {index} has invalid Injury id: {injury_id}")

    clinical_finding_id = _required_string(row, "clinical_finding_id", index)
    if not clinical_finding_id.startswith("snomedct:"):
        raise ValueError(
            f"Condition row {index} has invalid ClinicalFinding id: "
            f"{clinical_finding_id}"
        )

    target_kind = _target_kind(_required_string(row, "target_kind", index), index)
    target_id = _required_string(row, "target_id", index)
    expected_prefix = {
        "MovementPattern": "fkg:movement-pattern/",
        "Joint": "fkg:joint/",
    }[target_kind]
    if not target_id.startswith(expected_prefix):
        raise ValueError(
            f"Condition row {index} target id does not match {target_kind}: {target_id}"
        )

    citation_value = row.get("citation")
    if citation_value is None:
        raise ValueError(f"Condition row {index} requires one citation")
    if not isinstance(citation_value, dict):
        raise TypeError(f"Condition row {index} citation must be a JSON object")
    citation = _required_string(citation_value, "reference", index, "citation")
    citation_url = _required_string(citation_value, "url", index, "citation")
    if not citation_url.startswith("https://"):
        raise ValueError(f"Condition row {index} citation URL must use HTTPS")

    return ConditionRow(
        injury_id=injury_id,
        name=_required_string(row, "name", index),
        clinical_finding_id=clinical_finding_id,
        target_kind=target_kind,
        target_id=target_id,
        verdict=_verdict(_required_string(row, "verdict", index), index),
        note=_required_string(row, "note", index),
        citation=citation,
        citation_url=citation_url,
    )


def _object(value: Any, description: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(f"{description} must be a JSON object")
    return value


def _required_string(
    value: JsonObject, key: str, index: int, parent: str | None = None
) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        path = f"{parent}.{key}" if parent else key
        raise ValueError(f"Condition row {index} requires non-empty {path}")
    return item


def _target_kind(value: str, index: int) -> ContraindicationTarget:
    if value not in ("MovementPattern", "Joint"):
        raise ValueError(f"Condition row {index} has unsupported target kind: {value}")
    return value


def _verdict(value: str, index: int) -> AuthoredVerdict:
    if value not in ("exclude", "caution"):
        raise ValueError(f"Condition row {index} has unsupported verdict: {value}")
    return value
