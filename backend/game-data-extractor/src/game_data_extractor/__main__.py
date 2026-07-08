import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Final

from game_data_extractor import __version__
from game_data_extractor.data_contracts import (
    DatasetParseError,
    ImportDiagnostic,
    MilestoneDefinition,
    MilestoneFailure,
    MilestoneRecipeSet,
    OptimizerRecipeDataset,
    calculate_milestone_recipe_set,
    dataset_to_factory_data_package,
    load_milestone_definitions,
    technology_prerequisite_graph_json_value,
)
from game_data_extractor.data_raw_normalization import normalize_data_raw_dump
from game_data_extractor.dump_data import (
    DumpDataError,
    acquire_factorio_dump,
)
from game_data_extractor.dump_data_cli import parse_dump_data_request
from game_data_extractor.save_settings import (
    FixtureSaveModSettingsExtractor,
    SaveSettingsExtractionError,
)

USAGE: Final = """usage: game-data-extractor [-h] [--version] <command>

Factorio game data extraction and import workflow utilities.

options:
  -h, --help  show this help message and exit
  --version   show package version and exit

commands:
  validate-dataset PATH  validate an optimizer recipe dataset JSON file
  extract-save-settings --save PATH [--factorio-bin PATH] [--mod-directory PATH]
                        [--output PATH|--output-settings PATH] [--format json]
  dump-data --factorio-bin PATH --settings PATH --mod-directory PATH
            --output-dir PATH [--dry-run]
  normalize-dump --dump PATH --output PATH [--diagnostics PATH]
  export-milestone --dataset PATH --milestones PATH --milestone NAME [--output PATH]
  export-technology-graph --dataset PATH --output PATH
  export-factory-data --dataset PATH --demand ITEM=RATE/min
        [--accepted-input ITEM ...] --output PATH
  report --dataset PATH [--settings PATH] [--milestone-output PATH]
"""
EXTRACT_SAVE_SETTINGS_CONTEXT: Final = "extract-save-settings"
NORMALIZE_DUMP_CONTEXT: Final = "normalize-dump"
EXPORT_MILESTONE_CONTEXT: Final = "export-milestone"
EXPORT_TECHNOLOGY_GRAPH_CONTEXT: Final = "export-technology-graph"
REPORT_CONTEXT: Final = "report"
EXPORT_FACTORY_DATA_CONTEXT: Final = "export-factory-data"
MAX_REPORTED_RECIPE_NAMES: Final = 10


@dataclass(frozen=True, slots=True)
class _ExtractSaveSettingsArguments:
    save_path: Path
    factorio_executable: Path | None
    mod_directory: Path | None
    output_path: Path | None
    output_format: str


@dataclass(frozen=True, slots=True)
class _NormalizeDumpArguments:
    dump_path: Path
    output_path: Path
    diagnostics_path: Path | None


@dataclass(frozen=True, slots=True)
class _ExportMilestoneArguments:
    dataset_path: Path
    milestones_path: Path
    milestone_name: str
    output_path: Path | None


@dataclass(frozen=True, slots=True)
class _ExportTechnologyGraphArguments:
    dataset_path: Path
    output_path: Path


@dataclass(frozen=True, slots=True)
class _ReportArguments:
    dataset_path: Path
    settings_path: Path | None
    milestone_output_path: Path | None


@dataclass(frozen=True, slots=True)
class _ExportFactoryDataArguments:
    dataset_path: Path
    demands_per_minute: Mapping[str, float]
    accepted_inputs: Sequence[str] | None
    output_path: Path


def main(arguments: Sequence[str] | None = None) -> int:  # noqa: C901, PLR0911
    parsed_arguments = sys.argv[1:] if arguments is None else list(arguments)

    if parsed_arguments in ([], ["-h"], ["--help"]):
        sys.stdout.write(USAGE)
        return 0

    if parsed_arguments == ["--version"]:
        sys.stdout.write(f"{__version__}\n")
        return 0

    if parsed_arguments[:1] == ["validate-dataset"]:
        return _validate_dataset(parsed_arguments[1:])

    if parsed_arguments[:1] == ["extract-save-settings"]:
        return _extract_save_settings(parsed_arguments[1:])

    if parsed_arguments[:1] == ["dump-data"]:
        return _dump_data(parsed_arguments[1:])

    if parsed_arguments[:1] == ["normalize-dump"]:
        return _normalize_dump(parsed_arguments[1:])

    if parsed_arguments[:1] == ["export-milestone"]:
        return _export_milestone(parsed_arguments[1:])

    if parsed_arguments[:1] == ["export-technology-graph"]:
        return _export_technology_graph(parsed_arguments[1:])

    if parsed_arguments[:1] == ["export-factory-data"]:
        return _export_factory_data(parsed_arguments[1:])

    if parsed_arguments[:1] == ["report"]:
        return _report(parsed_arguments[1:])

    unknown_command = parsed_arguments[0]
    sys.stderr.write(f"error: unknown command: {unknown_command}\n")
    sys.stderr.write(USAGE)
    return 2


def _validate_dataset(arguments: Sequence[str]) -> int:
    if len(arguments) != 1:
        sys.stderr.write("error: validate-dataset requires exactly one path\n")
        return 2

    path = Path(arguments[0])
    try:
        dataset = OptimizerRecipeDataset.from_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.stderr.write(f"error: dataset file not found: {path}\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"error: could not read dataset file: {error}\n")
        return 1
    except DatasetParseError as error:
        sys.stderr.write(f"error: invalid dataset: {error}\n")
        return 1

    sys.stdout.write(
        "valid dataset: "
        f"{len(dataset.items)} items, "
        f"{len(dataset.recipes)} recipes, "
        f"{len(dataset.technologies)} technologies\n",
    )
    return 0


def _extract_save_settings(arguments: Sequence[str]) -> int:
    try:
        parsed_arguments = _parse_extract_save_settings_arguments(arguments)
    except DatasetParseError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2

    extractor = FixtureSaveModSettingsExtractor()
    try:
        result = extractor.extract(
            parsed_arguments.save_path,
            factorio_executable=parsed_arguments.factorio_executable,
            mod_directory=parsed_arguments.mod_directory,
        )
    except SaveSettingsExtractionError as error:
        _write_json_output(parsed_arguments.output_path, error.to_json())
        sys.stderr.write(f"error: {error}\n")
        return 1

    _write_json_output(parsed_arguments.output_path, result.to_json())
    sys.stdout.write(
        "extracted save settings: "
        f"{len(result.startup_settings)} startup settings, "
        f"{len(result.provenance.enabled_mods)} enabled mods\n",
    )
    return 0


def _dump_data(arguments: Sequence[str]) -> int:
    try:
        request = parse_dump_data_request(arguments)
        result = acquire_factorio_dump(request)
    except DatasetParseError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2
    except DumpDataError as error:
        sys.stderr.write(error.to_json())
        return 1

    sys.stdout.write(result.to_json())
    return 0


def _normalize_dump(arguments: Sequence[str]) -> int:
    try:
        parsed_arguments = _parse_normalize_dump_arguments(arguments)
        dataset = normalize_data_raw_dump(
            parsed_arguments.dump_path.read_text(encoding="utf-8"),
        )
    except FileNotFoundError as error:
        sys.stderr.write(f"error: dump file not found: {error.filename}\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"error: could not read dump file: {error}\n")
        return 1
    except DatasetParseError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1

    _write_json_output(parsed_arguments.output_path, dataset.to_json())
    if parsed_arguments.diagnostics_path is not None:
        diagnostics_json = OptimizerRecipeDataset(
            diagnostics=dataset.diagnostics,
        ).to_json_value()["diagnostics"]
        _write_json_output(
            parsed_arguments.diagnostics_path, _json_text(diagnostics_json)
        )
    sys.stdout.write(
        "normalized dump: "
        f"{len(dataset.items)} items, "
        f"{len(dataset.recipes)} recipes, "
        f"{len(dataset.technologies)} technologies, "
        f"{len(dataset.resource_sources)} resource sources\n",
    )
    return 0


def _export_milestone(arguments: Sequence[str]) -> int:
    try:
        parsed_arguments = _parse_export_milestone_arguments(arguments)
        dataset = OptimizerRecipeDataset.from_json(
            parsed_arguments.dataset_path.read_text(encoding="utf-8")
        )
        definitions = load_milestone_definitions(
            parsed_arguments.milestones_path.read_text(encoding="utf-8")
        )
        definition = _milestone_definition(definitions, parsed_arguments.milestone_name)
        result = calculate_milestone_recipe_set(dataset, definition)
        exported = _milestone_dataset(dataset, result)
    except FileNotFoundError as error:
        sys.stderr.write(f"error: file not found: {error.filename}\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"error: could not read or write milestone data: {error}\n")
        return 1
    except DatasetParseError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2
    except MilestoneFailure as error:
        sys.stderr.write(f"error: {error}\n")
        return 1

    _write_json_output(parsed_arguments.output_path, exported.to_json())
    sys.stdout.write(
        f"exported milestone {result.milestone}: {len(result.recipe_names)} recipes, "
        f"{len(result.diagnostics)} diagnostics\n"
    )
    return 0


def _report(arguments: Sequence[str]) -> int:
    try:
        parsed_arguments = _parse_report_arguments(arguments)
    except DatasetParseError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2

    try:
        dataset = OptimizerRecipeDataset.from_json(
            parsed_arguments.dataset_path.read_text(encoding="utf-8")
        )
        settings = _read_report_settings(parsed_arguments.settings_path)
        milestone = _read_report_milestone(parsed_arguments.milestone_output_path)
    except FileNotFoundError as error:
        missing = error.filename
        if missing == str(parsed_arguments.dataset_path):
            sys.stderr.write(f"error: dataset file not found: {missing}\n")
        else:
            sys.stderr.write(f"error: report input file not found: {missing}\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"error: could not read report input: {error}\n")
        return 1
    except DatasetParseError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2

    sys.stdout.write(_format_report(dataset, settings, milestone))
    return 0


def _export_factory_data(arguments: Sequence[str]) -> int:
    try:
        parsed = _parse_export_factory_data_arguments(arguments)
        dataset = OptimizerRecipeDataset.from_json(
            parsed.dataset_path.read_text(encoding="utf-8")
        )
        demands_per_second = {
            name: rate / 60.0 for name, rate in parsed.demands_per_minute.items()
        }
        package = dataset_to_factory_data_package(
            dataset,
            demands_per_second,
            parsed.accepted_inputs,
        )
        _write_json_output(parsed.output_path, package.to_json())
    except FileNotFoundError as error:
        sys.stderr.write(f"error: dataset file not found: {error.filename}\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"error: could not read or write factory data: {error}\n")
        return 1
    except DatasetParseError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2

    sys.stdout.write(
        f"exported factory data: {len(package.items)} items, "
        f"{len(package.recipes)} recipes\n"
    )
    return 0


def _export_technology_graph(arguments: Sequence[str]) -> int:
    try:
        parsed = _parse_export_technology_graph_arguments(arguments)
        dataset = OptimizerRecipeDataset.from_json(
            parsed.dataset_path.read_text(encoding="utf-8")
        )
        _write_json_output(
            parsed.output_path,
            _json_text(technology_prerequisite_graph_json_value(dataset)),
        )
    except FileNotFoundError as error:
        sys.stderr.write(f"error: dataset file not found: {error.filename}\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"error: could not read or write technology graph: {error}\n")
        return 1
    except DatasetParseError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2

    sys.stdout.write(
        f"exported technology graph: {len(dataset.technologies)} technologies\n"
    )
    return 0


def _read_report_settings(path: Path | None) -> OptimizerRecipeDataset | None:
    if path is None:
        return None
    value = _load_report_json(path)
    if isinstance(value, dict) and "provenance" in value:
        value = {
            "startup_settings": value.get("startup_settings", []),
            "save_settings_provenance": value.get("provenance"),
        }
    return OptimizerRecipeDataset.from_json(_json_text(value))


def _read_report_milestone(path: Path | None) -> MilestoneRecipeSet | None:
    if path is None:
        return None
    value = _load_report_json(path)
    if isinstance(value, dict) and "milestones" in value:
        milestones = OptimizerRecipeDataset.from_json(_json_text(value)).milestones
        return milestones[0] if milestones else None
    legacy_dataset = OptimizerRecipeDataset.from_json(
        _json_text({"milestones": [value]})
    )
    return legacy_dataset.milestones[0]


def _milestone_dataset(
    dataset: OptimizerRecipeDataset,
    result: MilestoneRecipeSet,
) -> OptimizerRecipeDataset:
    available_names = set(result.recipe_names)
    return OptimizerRecipeDataset(
        items=dataset.items,
        recipes=[
            recipe for recipe in dataset.recipes if recipe.name in available_names
        ],
        technologies=dataset.technologies,
        resource_sources=dataset.resource_sources,
        startup_settings=dataset.startup_settings,
        save_settings_provenance=dataset.save_settings_provenance,
        dump_provenance=dataset.dump_provenance,
        diagnostics=tuple(dataset.diagnostics) + tuple(result.diagnostics),
        milestones=(result,),
    )


def _load_report_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as error:
        reason = f"invalid report input JSON in {path}: {error.msg}"
        raise DatasetParseError(REPORT_CONTEXT, reason) from error


def _format_report(
    dataset: OptimizerRecipeDataset,
    settings: OptimizerRecipeDataset | None,
    milestone: MilestoneRecipeSet | None,
) -> str:
    settings_source = settings or dataset
    lines = ["Game data extractor import report", ""]
    lines.extend(_format_save_settings(settings_source))
    lines.extend(
        [
            "",
            "Normalized dataset counts:",
            f"  items: {len(dataset.items)}",
            f"  recipes: {len(dataset.recipes)}",
            f"  technologies: {len(dataset.technologies)}",
            f"  resource sources: {len(dataset.resource_sources)}",
            f"  dataset startup settings: {len(dataset.startup_settings)}",
        ]
    )
    lines.extend(_format_diagnostics(dataset.diagnostics, "Diagnostics"))
    if dataset.dump_provenance is not None:
        lines.extend(["", "Dump provenance:"])
        for key, value in dataset.dump_provenance.to_json_value().items():
            lines.append(f"  {key}: {value}")
    if milestone is not None:
        lines.extend(["", "Milestone recipe set:"])
        lines.append(f"  milestone: {milestone.milestone}")
        lines.append(f"  dataset recipes: {len(dataset.recipes)}")
        lines.append(f"  milestone recipes: {len(milestone.recipe_names)}")
        excluded_names = sorted(
            {recipe.name for recipe in dataset.recipes} - set(milestone.recipe_names)
        )
        lines.append(f"  excluded recipes: {len(excluded_names)}")
        if len(excluded_names) <= MAX_REPORTED_RECIPE_NAMES:
            names = ", ".join(excluded_names) if excluded_names else "none"
            lines.append(f"  excluded recipe names: {names}")
        lines.extend(
            _format_diagnostics(milestone.diagnostics, "  milestone diagnostics")
        )
    return "\n".join(lines) + "\n"


def _format_save_settings(dataset: OptimizerRecipeDataset) -> list[str]:
    provenance = dataset.save_settings_provenance
    if provenance is None:
        return ["Save settings provenance:", "  not present"]
    return [
        "Save settings provenance:",
        f"  save: {provenance.save_name}",
        f"  sha256: {provenance.save_sha256}",
        f"  factorio version: {provenance.factorio_version}",
        f"  acquisition method: {provenance.acquisition_method}",
        f"  enabled mods: {len(provenance.enabled_mods)}",
        f"  save settings startup settings: {len(dataset.startup_settings)}",
        f"  warnings: {len(provenance.warnings)}",
    ]


def _format_diagnostics(
    diagnostics: Sequence[ImportDiagnostic], heading: str
) -> list[str]:
    lines = ["", f"{heading}:"]
    if not diagnostics:
        lines.append("  none")
        return lines
    counts: dict[tuple[str, str], int] = {}
    for diagnostic in diagnostics:
        severity: str = diagnostic.severity
        code = diagnostic.code
        counts[(severity, code)] = counts.get((severity, code), 0) + 1
    for (severity, code), count in sorted(counts.items()):
        lines.append(f"  {severity} {code}: {count}")
    return lines


def _parse_extract_save_settings_arguments(
    arguments: Sequence[str],
) -> _ExtractSaveSettingsArguments:
    save_path: Path | None = None
    factorio_executable: Path | None = None
    mod_directory: Path | None = None
    output_path: Path | None = None
    output_format = "json"
    index = 0

    while index < len(arguments):
        flag = arguments[index]
        match flag:
            case "--save":
                save_path = Path(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXTRACT_SAVE_SETTINGS_CONTEXT,
                    )
                )
                index += 2
            case "--factorio-bin":
                factorio_executable = Path(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXTRACT_SAVE_SETTINGS_CONTEXT,
                    )
                )
                index += 2
            case "--mod-directory":
                mod_directory = Path(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXTRACT_SAVE_SETTINGS_CONTEXT,
                    )
                )
                index += 2
            case "--output" | "--output-settings":
                output_path = Path(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXTRACT_SAVE_SETTINGS_CONTEXT,
                    )
                )
                index += 2
            case "--format":
                output_format = _flag_value(
                    arguments,
                    index,
                    flag,
                    context=EXTRACT_SAVE_SETTINGS_CONTEXT,
                )
                index += 2
            case _:
                reason = f"unknown flag {flag}"
                raise DatasetParseError(EXTRACT_SAVE_SETTINGS_CONTEXT, reason)

    if save_path is None:
        reason = "--save is required"
        raise DatasetParseError(EXTRACT_SAVE_SETTINGS_CONTEXT, reason)
    if output_format != "json":
        reason = "only --format json is supported"
        raise DatasetParseError(EXTRACT_SAVE_SETTINGS_CONTEXT, reason)

    return _ExtractSaveSettingsArguments(
        save_path=save_path,
        factorio_executable=factorio_executable,
        mod_directory=mod_directory,
        output_path=output_path,
        output_format=output_format,
    )


def _parse_normalize_dump_arguments(
    arguments: Sequence[str],
) -> _NormalizeDumpArguments:
    dump_path: Path | None = None
    output_path: Path | None = None
    diagnostics_path: Path | None = None
    index = 0

    while index < len(arguments):
        flag = arguments[index]
        match flag:
            case "--dump":
                dump_path = Path(
                    _flag_value(arguments, index, flag, context=NORMALIZE_DUMP_CONTEXT)
                )
                index += 2
            case "--output":
                output_path = Path(
                    _flag_value(arguments, index, flag, context=NORMALIZE_DUMP_CONTEXT)
                )
                index += 2
            case "--diagnostics":
                diagnostics_path = Path(
                    _flag_value(arguments, index, flag, context=NORMALIZE_DUMP_CONTEXT)
                )
                index += 2
            case _:
                reason = f"unknown flag {flag}"
                raise DatasetParseError(NORMALIZE_DUMP_CONTEXT, reason)

    if dump_path is None:
        reason = "--dump is required"
        raise DatasetParseError(NORMALIZE_DUMP_CONTEXT, reason)
    if output_path is None:
        reason = "--output is required"
        raise DatasetParseError(NORMALIZE_DUMP_CONTEXT, reason)
    return _NormalizeDumpArguments(
        dump_path=dump_path,
        output_path=output_path,
        diagnostics_path=diagnostics_path,
    )


def _parse_export_milestone_arguments(
    arguments: Sequence[str],
) -> _ExportMilestoneArguments:
    dataset_path: Path | None = None
    milestones_path: Path | None = None
    milestone_name: str | None = None
    output_path: Path | None = None
    index = 0

    while index < len(arguments):
        flag = arguments[index]
        match flag:
            case "--dataset":
                dataset_path = Path(
                    _flag_value(
                        arguments, index, flag, context=EXPORT_MILESTONE_CONTEXT
                    )
                )
                index += 2
            case "--milestones":
                milestones_path = Path(
                    _flag_value(
                        arguments, index, flag, context=EXPORT_MILESTONE_CONTEXT
                    )
                )
                index += 2
            case "--milestone":
                milestone_name = _flag_value(
                    arguments, index, flag, context=EXPORT_MILESTONE_CONTEXT
                )
                index += 2
            case "--output":
                output_path = Path(
                    _flag_value(
                        arguments, index, flag, context=EXPORT_MILESTONE_CONTEXT
                    )
                )
                index += 2
            case _:
                reason = f"unknown flag {flag}"
                raise DatasetParseError(EXPORT_MILESTONE_CONTEXT, reason)

    if dataset_path is None:
        raise DatasetParseError(EXPORT_MILESTONE_CONTEXT, "--dataset is required")
    if milestones_path is None:
        raise DatasetParseError(EXPORT_MILESTONE_CONTEXT, "--milestones is required")
    if milestone_name is None:
        raise DatasetParseError(EXPORT_MILESTONE_CONTEXT, "--milestone is required")
    return _ExportMilestoneArguments(
        dataset_path=dataset_path,
        milestones_path=milestones_path,
        milestone_name=milestone_name,
        output_path=output_path,
    )


def _parse_report_arguments(arguments: Sequence[str]) -> _ReportArguments:
    dataset_path: Path | None = None
    settings_path: Path | None = None
    milestone_output_path: Path | None = None
    index = 0

    while index < len(arguments):
        flag = arguments[index]
        match flag:
            case "--dataset":
                dataset_path = Path(
                    _flag_value(arguments, index, flag, context=REPORT_CONTEXT)
                )
                index += 2
            case "--settings":
                settings_path = Path(
                    _flag_value(arguments, index, flag, context=REPORT_CONTEXT)
                )
                index += 2
            case "--milestone-output":
                milestone_output_path = Path(
                    _flag_value(arguments, index, flag, context=REPORT_CONTEXT)
                )
                index += 2
            case _:
                raise DatasetParseError(REPORT_CONTEXT, f"unknown flag {flag}")

    if dataset_path is None:
        raise DatasetParseError(REPORT_CONTEXT, "--dataset is required")
    return _ReportArguments(
        dataset_path=dataset_path,
        settings_path=settings_path,
        milestone_output_path=milestone_output_path,
    )


def _parse_export_factory_data_arguments(
    arguments: Sequence[str],
) -> _ExportFactoryDataArguments:
    dataset_path: Path | None = None
    output_path: Path | None = None
    demands: dict[str, float] = {}
    accepted_inputs: list[str] = []
    explicit_accepted_inputs = False
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        match flag:
            case "--dataset":
                dataset_path = Path(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXPORT_FACTORY_DATA_CONTEXT,
                    )
                )
                index += 2
            case "--demand":
                name, rate = _parse_demand(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXPORT_FACTORY_DATA_CONTEXT,
                    ),
                    context=EXPORT_FACTORY_DATA_CONTEXT,
                )
                demands[name] = rate
                index += 2
            case "--accepted-input":
                accepted_inputs.append(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXPORT_FACTORY_DATA_CONTEXT,
                    )
                )
                explicit_accepted_inputs = True
                index += 2
            case "--output":
                output_path = Path(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXPORT_FACTORY_DATA_CONTEXT,
                    )
                )
                index += 2
            case _:
                raise DatasetParseError(
                    EXPORT_FACTORY_DATA_CONTEXT,
                    f"unknown flag {flag}",
                )
    if dataset_path is None:
        raise DatasetParseError(EXPORT_FACTORY_DATA_CONTEXT, "--dataset is required")
    if output_path is None:
        raise DatasetParseError(EXPORT_FACTORY_DATA_CONTEXT, "--output is required")
    if not demands:
        raise DatasetParseError(
            EXPORT_FACTORY_DATA_CONTEXT,
            "at least one --demand is required",
        )
    return _ExportFactoryDataArguments(
        dataset_path=dataset_path,
        demands_per_minute=demands,
        accepted_inputs=tuple(accepted_inputs) if explicit_accepted_inputs else None,
        output_path=output_path,
    )


def _parse_export_technology_graph_arguments(
    arguments: Sequence[str],
) -> _ExportTechnologyGraphArguments:
    dataset_path: Path | None = None
    output_path: Path | None = None
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        match flag:
            case "--dataset":
                dataset_path = Path(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXPORT_TECHNOLOGY_GRAPH_CONTEXT,
                    )
                )
                index += 2
            case "--output":
                output_path = Path(
                    _flag_value(
                        arguments,
                        index,
                        flag,
                        context=EXPORT_TECHNOLOGY_GRAPH_CONTEXT,
                    )
                )
                index += 2
            case _:
                raise DatasetParseError(
                    EXPORT_TECHNOLOGY_GRAPH_CONTEXT,
                    f"unknown flag {flag}",
                )
    if dataset_path is None:
        raise DatasetParseError(
            EXPORT_TECHNOLOGY_GRAPH_CONTEXT,
            "--dataset is required",
        )
    if output_path is None:
        raise DatasetParseError(
            EXPORT_TECHNOLOGY_GRAPH_CONTEXT,
            "--output is required",
        )
    return _ExportTechnologyGraphArguments(
        dataset_path=dataset_path,
        output_path=output_path,
    )


def _parse_demand(
    value: str,
    context: str = EXPORT_FACTORY_DATA_CONTEXT,
) -> tuple[str, float]:
    if "=" not in value:
        raise DatasetParseError(context, "--demand must be ITEM=RATE/min")
    item, rate_text = value.split("=", 1)
    rate_text = rate_text.removesuffix("/min")
    try:
        rate = float(rate_text)
    except ValueError as error:
        raise DatasetParseError(context, f"invalid demand rate {rate_text}") from error
    return item, rate


def _milestone_definition(
    definitions: Mapping[str, MilestoneDefinition],
    milestone_name: str,
) -> MilestoneDefinition:
    definition = definitions.get(milestone_name)
    if definition is None:
        reason = f"unknown milestone {milestone_name}"
        raise DatasetParseError(EXPORT_MILESTONE_CONTEXT, reason)
    return definition


def _flag_value(
    arguments: Sequence[str],
    index: int,
    flag: str,
    *,
    context: str,
) -> str:
    value_index = index + 1
    if value_index >= len(arguments):
        reason = f"{flag} requires a value"
        raise DatasetParseError(context, reason)
    value = arguments[value_index]
    if value.startswith("--"):
        reason = f"{flag} requires a value"
        raise DatasetParseError(context, reason)
    return value


def _write_json_output(output_path: Path | None, text: str) -> None:
    if output_path is None:
        sys.stdout.write(text)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def _json_text(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _nonzero(values: Mapping[str, float], tolerance: float = 1e-7) -> dict[str, float]:
    return {name: value for name, value in values.items() if abs(value) > tolerance}


if __name__ == "__main__":
    raise SystemExit(main())
