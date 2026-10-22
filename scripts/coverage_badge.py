"""Gera o JSON de badge (endpoint do shields.io) a partir do coverage.json do pytest-cov.

uv run pytest --cov-report=json
uv run python scripts/coverage_badge.py coverage.json site/badges/coverage.json
"""

import json
import sys
from pathlib import Path


def badge(percent: float) -> dict:
    color = "brightgreen" if percent >= 90 else "green" if percent >= 80 else "orange"
    return {
        "schemaVersion": 1,
        "label": "cobertura",
        "message": f"{percent:.0f}%",
        "color": color,
    }


def main(source: str, dest: str) -> None:
    percent = json.loads(Path(source).read_text())["totals"]["percent_covered"]
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_text(json.dumps(badge(percent)) + "\n", encoding="utf-8")
    print(f"cobertura {percent:.1f}% → {dest}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
