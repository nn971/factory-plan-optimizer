import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from game_data_extractor.data_contracts import (
    DatasetParseError,
    MilestoneDefinition,
    MilestoneFailure,
    MilestoneRecipeSet,
    OptimizerRecipeDataset,
    calculate_milestone_recipe_set,
    load_milestone_definitions,
)

from factory_plan_optimizer import __version__
from factory_plan_optimizer.planning import solve_planning_lp

USAGE: Final = """usage: python -m factory_plan_optimizer [-h] [--version] <command>

Experimental hierarchical factory-planning optimizer scaffold.

options:
  -h, --help  show this help message and exit
  --version   show package version and exit

commands:
  plan --dataset PATH [--milestones PATH --milestone NAME] --demand ITEM=RATE/min
        --output PATH [--allow-relax-inputs]
"""
PLAN_CONTEXT: Final = "plan"


@dataclass(frozen=True, slots=True)
class _PlanArguments:
    dataset_path: Path
    milestones_path: Path | None
    milestone_name: str | None
    demands_per_minute: Mapping[str, float]
    output_path: Path
    allow_relax_inputs: bool


def main(arguments: Sequence[str] | None = None) -> int:
    parsed_arguments = sys.argv[1:] if arguments is None else list(arguments)

    if parsed_arguments in ([], ["-h"], ["--help"]):
        sys.stdout.write(USAGE)
        return 0

    if parsed_arguments == ["--version"]:
        sys.stdout.write(f"{__version__}\n")
        return 0

    if parsed_arguments[:1] == ["plan"]:
        return _plan(parsed_arguments[1:])

    unknown_command = parsed_arguments[0]
    sys.stderr.write(f"error: unknown command: {unknown_command}\n")
    sys.stderr.write(USAGE)
    return 2


def _plan(arguments: Sequence[str]) -> int:
    try:
        parsed = _parse_plan_arguments(arguments)
        dataset = OptimizerRecipeDataset.from_json(
            parsed.dataset_path.read_text(encoding="utf-8")
        )
        _validate_plan_milestone_pair(parsed)
        if parsed.milestones_path is not None and parsed.milestone_name is not None:
            definitions = load_milestone_definitions(
                parsed.milestones_path.read_text(encoding="utf-8")
            )
            definition = _milestone_definition(definitions, parsed.milestone_name)
            dataset = _milestone_dataset(
                dataset,
                calculate_milestone_recipe_set(dataset, definition),
            )
        demands_per_second = {
            name: rate / 60.0 for name, rate in parsed.demands_per_minute.items()
        }
        plan = solve_planning_lp(
            dataset,
            demands_per_second,
            allow_relax_inputs=parsed.allow_relax_inputs,
        )
    except FileNotFoundError as error:
        sys.stderr.write(f"error: file not found: {error.filename}\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"error: could not read or write plan data: {error}\n")
        return 1
    except (DatasetParseError, MilestoneFailure) as error:
        sys.stderr.write(f"error: {error}\n")
        return 2

    result = plan.result
    output = {
        "status": result.status,
        "demands_per_minute": dict(parsed.demands_per_minute),
        "demands_per_second": demands_per_second,
        "selected_recipe_rates_per_second": _nonzero(result.recipe_rates),
        "raw_external_inputs_per_second": _nonzero(result.external_supplies),
        "unmet_demand_per_second": _nonzero(result.unmet_demand),
        "objective_components": dict(result.objective_components),
        "objective_value": result.objective_value,
        "max_abs_balance_residual": max(
            (abs(value) for value in result.balance_residuals.values()),
            default=0.0,
        ),
        "accepted_inputs": sorted(plan.package.external_supplies),
        "accepted_input_policy": plan.accepted_input_policy,
        "relaxation_steps": [
            {
                "added_input": step.added_input,
                "status": step.status,
                "unmet_demand": dict(step.unmet_demand),
                "selected_recipe_count": step.selected_recipe_count,
            }
            for step in plan.relaxation_steps
        ],
        "input_counts": {
            "items": len(dataset.items),
            "recipes": len(dataset.recipes),
            "resource_sources": len(dataset.resource_sources),
        },
        "message": result.message,
        "details": result.details,
    }
    _write_json_output(parsed.output_path, _json_text(output))
    sys.stdout.write(
        f"planned {len(_nonzero(result.recipe_rates))} recipes, "
        f"status {result.status}\n"
    )
    return 0


def _validate_plan_milestone_pair(parsed: _PlanArguments) -> None:
    if (parsed.milestones_path is None) != (parsed.milestone_name is None):
        raise DatasetParseError(
            PLAN_CONTEXT,
            "--milestones and --milestone must be provided together",
        )


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


def _parse_plan_arguments(arguments: Sequence[str]) -> _PlanArguments:  # noqa: C901
    dataset_path: Path | None = None
    milestones_path: Path | None = None
    milestone_name: str | None = None
    output_path: Path | None = None
    demands: dict[str, float] = {}
    allow_relax_inputs = False
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        match flag:
            case "--dataset":
                dataset_path = Path(_flag_value(arguments, index, flag))
                index += 2
            case "--milestones":
                milestones_path = Path(_flag_value(arguments, index, flag))
                index += 2
            case "--milestone":
                milestone_name = _flag_value(arguments, index, flag)
                index += 2
            case "--demand":
                name, rate = _parse_demand(_flag_value(arguments, index, flag))
                demands[name] = rate
                index += 2
            case "--output":
                output_path = Path(_flag_value(arguments, index, flag))
                index += 2
            case "--allow-relax-inputs":
                allow_relax_inputs = True
                index += 1
            case _:
                raise DatasetParseError(PLAN_CONTEXT, f"unknown flag {flag}")
    if dataset_path is None:
        raise DatasetParseError(PLAN_CONTEXT, "--dataset is required")
    if output_path is None:
        raise DatasetParseError(PLAN_CONTEXT, "--output is required")
    if not demands:
        raise DatasetParseError(PLAN_CONTEXT, "at least one --demand is required")
    return _PlanArguments(
        dataset_path,
        milestones_path,
        milestone_name,
        demands,
        output_path,
        allow_relax_inputs,
    )


def _parse_demand(value: str) -> tuple[str, float]:
    if "=" not in value:
        raise DatasetParseError(PLAN_CONTEXT, "--demand must be ITEM=RATE/min")
    item, rate_text = value.split("=", 1)
    rate_text = rate_text.removesuffix("/min")
    try:
        rate = float(rate_text)
    except ValueError as error:
        reason = f"invalid demand rate {rate_text}"
        raise DatasetParseError(PLAN_CONTEXT, reason) from error
    return item, rate


def _milestone_definition(
    definitions: Mapping[str, MilestoneDefinition],
    milestone_name: str,
) -> MilestoneDefinition:
    definition = definitions.get(milestone_name)
    if definition is None:
        raise DatasetParseError(PLAN_CONTEXT, f"unknown milestone {milestone_name}")
    return definition


def _flag_value(arguments: Sequence[str], index: int, flag: str) -> str:
    value_index = index + 1
    if value_index >= len(arguments):
        raise DatasetParseError(PLAN_CONTEXT, f"{flag} requires a value")
    value = arguments[value_index]
    if value.startswith("--"):
        raise DatasetParseError(PLAN_CONTEXT, f"{flag} requires a value")
    return value


def _write_json_output(output_path: Path, text: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def _json_text(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _nonzero(values: Mapping[str, float], tolerance: float = 1e-7) -> dict[str, float]:
    return {name: value for name, value in values.items() if abs(value) > tolerance}


if __name__ == "__main__":
    raise SystemExit(main())
