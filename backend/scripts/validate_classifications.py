from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.data.normalization import ClassificationNormalizer


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[2]
    normalizer = ClassificationNormalizer(
        repo_root / "data/najiz-case-classifications-1447.json",
        repo_root / "data/classification_enrichment.json",
    )
    catalog = normalizer.normalize()
    print(
        json.dumps(
            catalog.validation_report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if catalog.validation_report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
