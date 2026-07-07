from __future__ import annotations

import ast
from pathlib import Path


def test_optimizer_core_does_not_reference_api_or_frontend() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    core_src = repo_root / "backend" / "optimizer-core" / "src"

    for path in core_src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "factory_plan_api" not in text
        assert "frontend" not in text


def test_api_does_not_import_optimizer_cli_modules() -> None:
    api_src = Path(__file__).resolve().parents[1] / "src"
    forbidden = (
        "factory_plan_optimizer.__main__",
        "factory_plan_optimizer.dump_data_cli",
        "factory_plan_optimizer.dump_data",
    )

    for path in api_src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden_import in forbidden:
            assert forbidden_import not in text


def test_api_imports_only_extractor_contracts() -> None:
    api_src = Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []

    for path in api_src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported_modules: list[str] = []
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.append(node.module)

            offenders.extend(
                f"{path}: {module}"
                for module in imported_modules
                if module == "game_data_extractor"
                or (
                    module.startswith("game_data_extractor.")
                    and not module.startswith("game_data_extractor.data_contracts")
                )
            )

    assert offenders == []
