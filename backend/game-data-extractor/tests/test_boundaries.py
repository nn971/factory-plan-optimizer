from __future__ import annotations

import ast
from pathlib import Path


def test_data_contracts_do_not_import_workflow_or_optimizer_modules() -> None:
    contracts = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "game_data_extractor"
        / "data_contracts"
    )
    offenders: list[str] = []

    for module_path in contracts.rglob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders.extend(
                    f"{module_path}:{alias.name}"
                    for alias in node.names
                    if alias.name.startswith("game_data_extractor")
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("game_data_extractor") and not module.startswith(
                    "game_data_extractor.data_contracts"
                ):
                    offenders.append(f"{module_path}:{module}")

    assert offenders == []


def test_extractor_source_has_no_optimizer_or_solver_references() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src" / "game_data_extractor"
    prohibited = ("factory_plan_optimizer", "pyomo", "highspy")
    offenders: list[str] = []

    for module_path in src_root.rglob("*.py"):
        text = module_path.read_text(encoding="utf-8")
        offenders.extend(
            f"{module_path}:{prohibited_text}"
            for prohibited_text in prohibited
            if prohibited_text in text
        )

    assert offenders == []
