import subprocess
import sys

import factory_plan_optimizer


def test_package_imports() -> None:
    # Given: the package is installed or importable from the source tree.
    # When: the package metadata is inspected.
    version = factory_plan_optimizer.__version__

    # Then: a non-empty version string is available.
    assert version


def test_cli_help_exits_successfully() -> None:
    # Given: the CLI is invoked through the package module.
    command = [sys.executable, "-m", "factory_plan_optimizer", "--help"]

    # When: the help command is run.
    completed_process = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: help succeeds and prints usage text.
    assert completed_process.returncode == 0
    assert "usage:" in completed_process.stdout.lower()
