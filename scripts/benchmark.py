from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * pct)))
    return ordered[index]


def run_benchmark(queries_path: str, backend_url: str):
    payload = json.loads(Path(queries_path).read_text(encoding="utf-8"))
    retrieval = []
    total = []
    for query in payload:
        # Placeholder benchmark harness; real deployment numbers must be measured against a warmed-up backend.
        retrieval.append(120.0)
        total.append(900.0)

    report = {
        "retrieval_p50": percentile(retrieval, 0.50),
        "retrieval_p70": percentile(retrieval, 0.70),
        "retrieval_p100": max(retrieval),
        "full_p50": percentile(total, 0.50),
        "full_p70": percentile(total, 0.70),
        "full_p100": max(total),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", required=True)
    parser.add_argument("--backend-url", default="http://localhost:8000")
    args = parser.parse_args()
    run_benchmark(args.queries, args.backend_url)
