"""File and directory utility helpers."""

import json
from pathlib import Path
from typing import Any

def ensure_dir(path: Path) -> Path:
    """Create directory if not exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path

def read_json(path: Path, default: Any = None) -> Any:
    """Safely read JSON file."""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Safely write JSON file with indentation."""
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
