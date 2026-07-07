from importlib.metadata import PackageNotFoundError, version
from typing import Final

PACKAGE_NAME: Final = "factory-plan-optimizer"

try:
    __version__ = version(PACKAGE_NAME)
except PackageNotFoundError:
    __version__ = "0.0.0"
