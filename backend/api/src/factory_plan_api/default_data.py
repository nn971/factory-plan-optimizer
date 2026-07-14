from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from game_data_extractor.data_contracts import (
    FactoryDataPackageParseError,
    load_factory_data_package,
)

from factory_plan_api.config import (
    DEFAULT_EXAMPLE_RELATIVE_PATH,
    GENERATED_DEFAULT_RELATIVE_PATH,
    example_default_data_path,
    generated_default_data_path,
)

if TYPE_CHECKING:
    from game_data_extractor.data_contracts import FactoryDataPackage

DEFAULT_DATA_PATH_ENV = "FACTORY_PLAN_DEFAULT_DATA_PATH"


def default_data_path() -> Path:
    """Return the configured or repository fallback default data path."""
    override = os.environ.get(DEFAULT_DATA_PATH_ENV)
    if override:
        return Path(override).expanduser().resolve()
    generated_default = generated_default_data_path()
    if generated_default.exists():
        return generated_default
    return example_default_data_path()


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
            for fallback in (example_default_data_path(),):
                if fallback.exists():
                    return _load_factory_data_path(fallback)
            raise
    return _load_factory_data_path(path)


def _load_factory_data_path(path: Path) -> FactoryDataPackage:
    return load_factory_data_package(path.read_text(encoding="utf-8"))


def _is_generated_default_path(path: Path) -> bool:
    return path.as_posix().endswith(GENERATED_DEFAULT_RELATIVE_PATH.as_posix())


__all__ = [
    "DEFAULT_DATA_PATH_ENV",
    "DEFAULT_EXAMPLE_RELATIVE_PATH",
    "GENERATED_DEFAULT_RELATIVE_PATH",
    "default_data_path",
    "load_default_factory_data",
]
