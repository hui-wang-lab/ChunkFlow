"""Generate Phase 5 golden package snapshots.

Run from the repository root:

    python -m scripts.generate_golden_fixtures
"""
from __future__ import annotations

import json
from pathlib import Path

from chunkflow.core.pipeline import PipelineConfig, parse_to_chunk_package
from chunkflow.core.snapshot import package_snapshot


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "test" / "fixtures"
GOLDEN = FIXTURES / "golden"


CASES = {
    "csv_table_data": (
        FIXTURES / "phase5_table.csv",
        PipelineConfig(parser="auto", template="auto", include_blocks=True),
    ),
    "markdown_qa": (
        FIXTURES / "phase5_qa.md",
        PipelineConfig(parser="auto", template="auto", include_blocks=True),
    ),
}


def main() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name, (path, config) in CASES.items():
        package = parse_to_chunk_package(path, config)
        target = GOLDEN / f"{name}.json"
        target.write_text(
            json.dumps(package_snapshot(package), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {target}")


if __name__ == "__main__":
    main()

