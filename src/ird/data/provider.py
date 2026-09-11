from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping


class FileDataProvider:
    """Read public exchange files without platform-specific rules."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[Mapping[str, Any]]:
        suffix = self.path.suffix.lower()
        if suffix == ".csv":
            with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        if suffix == ".json":
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
                raise ValueError("JSON data must be a list of objects")
            return data
        raise ValueError(f"unsupported data format: {suffix}")
