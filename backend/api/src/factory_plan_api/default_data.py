from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from factory_plan_optimizer.optimizer.factory_data_loader import (
    load_factory_data_package,
)

if TYPE_CHECKING:
    from factory_plan_optimizer.optimizer.models import FactoryDataPackage

DEFAULT_DATA_PATH_ENV = "FACTORY_PLAN_DEFAULT_DATA_PATH"


def default_data_path() -> Path:
    """Return the configured or repository fallback default data path."""
    override = os.environ.get(DEFAULT_DATA_PATH_ENV)
    if override:
        return Path(override).expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[4]
    return repository_root / "examples" / "data" / "toy_iron.factory-data.json"


def load_default_factory_data() -> FactoryDataPackage:
    """Load the API default factory data package independent of process CWD."""
    return load_factory_data_package(default_data_path().read_text(encoding="utf-8"))
