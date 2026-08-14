import json
from dataclasses import asdict

from app.graph.ingest import ingest_kg1, ingest_kg2


def main() -> None:
    counts = {
        "kg1": asdict(ingest_kg1()),
        "kg2": asdict(ingest_kg2()),
    }
    print(json.dumps(counts, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
