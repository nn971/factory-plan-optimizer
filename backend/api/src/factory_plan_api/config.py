from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_EXAMPLE_RELATIVE_PATH = Path("examples/data/toy_iron.factory-data.json")
GENERATED_DEFAULT_RELATIVE_PATH = Path("data/generated/default.factory-data.json")


@dataclass(frozen=True, slots=True)
class ApiLimits:
    max_package_upload_bytes: int = 1_000_000
    max_stored_packages: int = 8
    max_solve_workers: int = 2
    max_active_jobs: int = 8
    max_retained_jobs: int = 64


DEFAULT_API_LIMITS = ApiLimits()


def repository_root() -> Path:
    """Return repository root from the installed API package location."""
    return Path(__file__).resolve().parents[4]


def generated_default_data_path() -> Path:
    return repository_root() / GENERATED_DEFAULT_RELATIVE_PATH


def example_default_data_path() -> Path:
    return repository_root() / DEFAULT_EXAMPLE_RELATIVE_PATH
