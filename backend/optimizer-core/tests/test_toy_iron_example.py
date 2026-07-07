from __future__ import annotations

import pytest
from game_data_extractor.data_contracts import (
    FactoryDataPackage,
    load_factory_data_package,
)

from factory_plan_optimizer.optimizer import solve_global_recipe_lp
from paths import EXAMPLES_DATA_ROOT

EXAMPLE_PATH = EXAMPLES_DATA_ROOT / "toy_iron.factory-data.json"
RESIDUAL_TOLERANCE = 1e-7


def test_toy_iron_example_loads_and_solves_exactly() -> None:
    package = load_factory_data_package(EXAMPLE_PATH.read_text(encoding="utf-8"))

    result = solve_global_recipe_lp(package)

    assert result.status == "optimal"
    assert result.recipe_rates == pytest.approx(
        {
            "smelt-iron": 10.0,
            "make-gear": 5.0,
        },
    )
    assert result.external_supplies == pytest.approx(
        {
            "iron-ore": 10.0,
            "iron-plate": 0.0,
            "iron-gear": 0.0,
        },
    )
    assert result.unmet_demand == pytest.approx(
        {
            "iron-ore": 0.0,
            "iron-plate": 0.0,
            "iron-gear": 0.0,
        },
    )
    assert result.surplus == pytest.approx(
        {
            "iron-ore": 0.0,
            "iron-plate": 0.0,
            "iron-gear": 0.0,
        },
    )
    assert result.objective_components == pytest.approx(
        {
            "raw_cost": 10.0,
            "production_cost": 12.5,
            "flow_cost": 0.0,
            "port_cost": 0.0,
            "cluster_cost": 0.0,
            "duplication_cost": 0.0,
            "unmet_demand_penalty": 0.0,
        },
    )
    assert result.objective_value == pytest.approx(22.5)
    assert all(
        abs(residual) < RESIDUAL_TOLERANCE
        for residual in result.balance_residuals.values()
    )


def test_toy_iron_example_roundtrips_through_canonical_json() -> None:
    package = FactoryDataPackage.from_json(EXAMPLE_PATH.read_text(encoding="utf-8"))

    reparsed = FactoryDataPackage.from_json(package.to_json())

    assert reparsed.to_json_value() == package.to_json_value()
