from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type CoefficientKind = Literal["input", "output"]
type DiagnosticSeverity = Literal["info", "warning", "error"]
type PrototypeType = Literal["item", "fluid"]


@dataclass(frozen=True, slots=True)
class DatasetParseError(Exception):
    context: str
    reason: str

    def __str__(self) -> str:
        return f"{self.context}: {self.reason}"
