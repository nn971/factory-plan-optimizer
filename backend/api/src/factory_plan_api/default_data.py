from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from game_data_extractor.data_contracts import (
    FactoryDataPackageParseError,
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
    if os.environ.get(DEFAULT_DATA_PATH_ENV):
        return _load_factory_data_path(path)
    if _is_generated_default_path(path):
        try:
            return _load_factory_data_path(path)
        except FactoryDataPackageParseError:
            # Generated defaults are ignored locally and may be stale across schema
            # changes. Fall back to versioned curated/example defaults for tests and
            # dev startup; explicit env overrides still raise parse errors above.
            repository_root = Path(__file__).resolve().parents[4]
            for fallback in (
                repository_root / CURATED_DEFAULT_RELATIVE_PATH,
                repository_root / "examples" / "data" / "toy_iron.factory-data.json",
            ):
                if fallback.exists():
                    return _load_factory_data_path(fallback)
            raise
    return _load_factory_data_path(path)


def _load_factory_data_path(path: Path) -> FactoryDataPackage:
    return load_factory_data_package(path.read_text(encoding="utf-8"))


def _is_generated_default_path(path: Path) -> bool:
    return path.as_posix().endswith(GENERATED_DEFAULT_RELATIVE_PATH.as_posix())
