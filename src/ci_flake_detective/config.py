"""Configuration loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import DetectiveConfig


def load_config(path: Optional[str] = None) -> DetectiveConfig:
    if not path:
        return DetectiveConfig.defaults()
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("config root must be a JSON object")
    return DetectiveConfig.from_dict(data)

