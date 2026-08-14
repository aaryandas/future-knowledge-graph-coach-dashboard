import json
import shutil
from pathlib import Path

import pytest
from app.graph.ingest import ingest_kg1

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = REPOSITORY_ROOT / "data"


def test_ingest_kg1_rejects_uncited_condition_row(tmp_path: Path) -> None:
    data_directory = tmp_path / "data"
    shutil.copytree(DATA_DIRECTORY, data_directory)
    conditions_path = data_directory / "conditions.json"
    conditions = json.loads(conditions_path.read_bytes())
    del conditions[0]["citation"]
    conditions_path.write_text(json.dumps(conditions))

    with pytest.raises(ValueError, match="Condition row 0 requires one citation"):
        ingest_kg1(data_directory)
