from __future__ import annotations

from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = CORE_ROOT.parents[1]
CORE_SRC_ROOT = CORE_ROOT / "src"
FIXTURES_ROOT = CORE_ROOT / "tests" / "fixtures"
EXAMPLES_DATA_ROOT = REPOSITORY_ROOT / "examples" / "data"
