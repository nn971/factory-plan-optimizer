from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from game_data_extractor.data_contracts import (
    load_factory_data_package,
)

if TYPE_CHECKING:
    from game_data_extractor.data_contracts import FactoryDataPackage

DEFAULT_DATA_PATH_ENV = "FACTORY_PLAN_DEFAULT_DATA_PATH"
GENERATED_DEFAULT_RELATIVE_PATH = Path(
    "data/generated/real-plan-test/logistic-science.factory-data.json",
)
CURATED_DEFAULT_RELATIVE_PATH = Path("data/packages/default.factory-data.json")


def default_data_path() -> Path:
    """Return the configured or repository fallback default data path."""
    override = os.environ.get(DEFAULT_DATA_PATH_ENV)
    if override:
        return Path(override).expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[4]
    generated_default = repository_root / GENERATED_DEFAULT_RELATIVE_PATH
    if generated_default.exists():
        return generated_default
    curated_default = repository_root / CURATED_DEFAULT_RELATIVE_PATH
    if curated_default.exists():
        return curated_default
    return repository_root / "examples" / "data" / "toy_iron.factory-data.json"


def load_default_factory_data() -> FactoryDataPackage:
    """Load the API default factory data package independent of process CWD."""
    path = default_data_path()
    text = path.read_text(encoding="utf-8")
    if _is_generated_default_path(path):
        text = _deduplicate_generated_parameter_items(text)
    return load_factory_data_package(text)


def _is_generated_default_path(path: Path) -> bool:
    return path.as_posix().endswith(GENERATED_DEFAULT_RELATIVE_PATH.as_posix())


def _deduplicate_generated_parameter_items(text: str) -> str:
    """Temporarily tolerate duplicate generated parameter pseudo-items.

    The current generated real-game package contains duplicate `parameter-*` item
    IDs with both item/fluid kinds. Keep the first occurrence so the canonical
    loader can read the package without changing normal package validation.
    """
    package = json.loads(text)
    items = package.get("items")
    if not isinstance(items, list):
        return text
    seen: set[str] = set()
    deduplicated: list[object] = []
    for item in items:
        if not isinstance(item, dict):
            deduplicated.append(item)
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str):
            deduplicated.append(item)
            continue
        if item_id in seen and item_id.startswith("parameter-"):
            continue
        seen.add(item_id)
        deduplicated.append(item)
    package["items"] = deduplicated
    return json.dumps(package)
