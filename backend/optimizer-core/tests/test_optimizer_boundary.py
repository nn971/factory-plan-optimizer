import ast

from paths import CORE_SRC_ROOT


def test_optimizer_modules_do_not_import_importer_modules() -> None:
    optimizer_path = CORE_SRC_ROOT / "factory_plan_optimizer" / "optimizer"
    offenders: list[str] = []

    for module_path in optimizer_path.rglob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders.extend(
                    f"{module_path}:{alias.name}"
                    for alias in node.names
                    if alias.name.startswith("factory_plan_optimizer.import_")
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("factory_plan_optimizer.import_"):
                    offenders.append(f"{module_path}:{module}")

    assert offenders == []


def test_optimizer_core_imports_only_extractor_contracts() -> None:
    offenders: list[str] = []
    for module_path in CORE_SRC_ROOT.rglob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders.extend(
                    f"{module_path}:{alias.name}"
                    for alias in node.names
                    if alias.name.startswith("game_data_extractor")
                    and not alias.name.startswith("game_data_extractor.data_contracts")
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("game_data_extractor") and not module.startswith(
                    "game_data_extractor.data_contracts"
                ):
                    offenders.append(f"{module_path}:{module}")

    assert offenders == []
