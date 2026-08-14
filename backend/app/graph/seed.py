import json
from dataclasses import asdict

from app.graph.ingest import ingest_kg1


def main() -> None:
    counts = ingest_kg1()
    print(json.dumps(asdict(counts), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
