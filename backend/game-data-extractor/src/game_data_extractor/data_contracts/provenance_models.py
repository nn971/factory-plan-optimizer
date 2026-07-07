from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game_data_extractor.data_contracts.types import DiagnosticSeverity, JsonValue


@dataclass(frozen=True, slots=True)
class StartupSetting:
    name: str
    value: str
    setting_type: str = "startup"

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "setting_type": self.setting_type,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class SaveSettingsProvenance:
    save_name: str
    save_sha256: str
    factorio_version: str | None = None
    enabled_mods: Sequence[str] = ()
    enabled_mod_versions: Mapping[str, str] = MappingProxyType({})
    warnings: Sequence[str] = ()
    acquisition_method: str = "save-settings-artifact"
    factorio_executable: str | None = None
    mod_directory: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled_mods", tuple(self.enabled_mods))
        object.__setattr__(
            self,
            "enabled_mod_versions",
            MappingProxyType(dict(sorted(self.enabled_mod_versions.items()))),
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "acquisition_method": self.acquisition_method,
            "enabled_mods": list(self.enabled_mods),
            "enabled_mod_versions": dict(self.enabled_mod_versions),
            "factorio_executable": self.factorio_executable,
            "factorio_version": self.factorio_version,
            "mod_directory": self.mod_directory,
            "save_name": self.save_name,
            "save_sha256": self.save_sha256,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class DumpProvenance:
    factorio_executable: str
    dump_path: str
    command: Sequence[str]
    settings_artifact: str | None = None
    staged_settings_path: str | None = None
    mod_directory: str | None = None
    output_directory: str | None = None
    dry_run: bool = False
    factorio_version: str | None = None
    save_name: str | None = None
    save_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "command": list(self.command),
            "dump_path": self.dump_path,
            "dry_run": self.dry_run,
            "factorio_executable": self.factorio_executable,
            "factorio_version": self.factorio_version,
            "mod_directory": self.mod_directory,
            "output_directory": self.output_directory,
            "save_name": self.save_name,
            "save_sha256": self.save_sha256,
            "settings_artifact": self.settings_artifact,
            "staged_settings_path": self.staged_settings_path,
        }


@dataclass(frozen=True, slots=True)
class ImportDiagnostic:
    severity: DiagnosticSeverity
    code: str
    message: str
    subject: str | None = None

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "subject": self.subject,
        }


@dataclass(frozen=True, slots=True)
class MilestoneDefinition:
    name: str
    completed_technologies: Sequence[str]
    include_hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "completed_technologies",
            tuple(self.completed_technologies),
        )

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "completed_technologies": list(self.completed_technologies),
            "include_hidden": self.include_hidden,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class MilestoneRecipeSet:
    milestone: str
    recipe_names: Sequence[str]
    diagnostics: Sequence[ImportDiagnostic] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_names", tuple(self.recipe_names))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "diagnostics": [
                diagnostic.to_json_value() for diagnostic in self.diagnostics
            ],
            "milestone": self.milestone,
            "recipe_names": list(self.recipe_names),
        }
