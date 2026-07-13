from __future__ import annotations

import time
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.testclient import TestClient

from factory_plan_api.app import app
from factory_plan_api.default_data import (
    DEFAULT_DATA_PATH_ENV,
    GENERATED_DEFAULT_RELATIVE_PATH,
    default_data_path,
    load_default_factory_data,
)
from factory_plan_api.jobs import SolveJobStoreFullError
from factory_plan_api.problem import result_to_dto

if TYPE_CHECKING:
    import pytest
    from game_data_extractor.data_contracts import FactoryDataPackage

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_PAYLOAD_TOO_LARGE = 413
HTTP_TOO_MANY_REQUESTS = 429
HTTP_UNPROCESSABLE_ENTITY = 422
DEFAULT_PACKAGE_ID = "default-first-3-science-v1"
DEFAULT_SCENARIO_ID = "first-3-science-v1"
DEFAULT_EXTERNAL_INPUT_CAPACITY = 100000.0
CURATED_SCIENCE_TARGETS = [
    "automation-science-pack",
    "logistic-science-pack",
    "py-science-pack-1",
]
FIRST_SIX_SCIENCE_TARGETS = [
    "automation-science-pack",
    "py-science-pack-1",
    "logistic-science-pack",
    "py-science-pack-2",
    "military-science-pack",
    "chemical-science-pack",
]
SCIENCE_TEST_RATE = 2.0
UNPRODUCIBLE_WATER_DEMAND = 2.0
UNPRODUCIBLE_WATER_PENALTY = 2000.0


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _curated_default_path() -> Path:
    return Path(__file__).parent / "fixtures" / "curated-default.factory-data.json"


def _water_package(demand: float = 2.0) -> dict[str, Any]:
    return {
        "schema_version": "factory-data-v2",
        "items": [{"id": "water", "kind": "fluid"}],
        "recipes": [
            {
                "id": "pump-water",
                "coefficients": {"water": 1.0},
                "energy_required": 1.0,
                "ingredients": [],
                "results": [{"type": "fluid", "name": "water", "amount": 1.0}],
                "production_cost": 0.0,
                "source_prototype_type": "boiler",
                "source_prototype_name": "offshore-pumpish-boiler",
            },
        ],
        "final_demands": {"water": demand},
        "external_supplies": {},
        "unmet_demand_penalty_rate": 1000.0,
    }


def _unproducible_water_package(demand: float = 2.0) -> dict[str, Any]:
    package = _water_package(demand)
    package["items"].append({"id": "stone", "kind": "item"})
    package["recipes"] = [
        {
            "id": "filter-water",
            "coefficients": {"stone": -1.0, "water": 1.0},
            "energy_required": 1.0,
            "ingredients": [{"type": "item", "name": "stone", "amount": 1.0}],
            "results": [{"type": "fluid", "name": "water", "amount": 1.0}],
            "production_cost": 0.0,
        },
    ]
    return package


def _coal_and_raw_coal_package() -> dict[str, Any]:
    return {
        "schema_version": "factory-data-v2",
        "items": [
            {"id": "raw-coal", "kind": "item"},
            {"id": "coal", "kind": "item"},
            {"id": "charcoal", "kind": "item"},
        ],
        "recipes": [
            {
                "id": "make-charcoal",
                "coefficients": {"coal": -1.0, "charcoal": 1.0},
                "energy_required": 1.0,
                "ingredients": [{"type": "item", "name": "coal", "amount": 1.0}],
                "results": [{"type": "item", "name": "charcoal", "amount": 1.0}],
                "production_cost": 0.0,
            },
        ],
        "final_demands": {"charcoal": 1.0},
        "external_supplies": {
            "raw-coal": {"cost": 1.0, "capacity": 10.0},
            "coal": {"cost": 2.0, "capacity": 10.0},
        },
        "unmet_demand_penalty_rate": 1000.0,
    }


def _milestone_filter_package() -> dict[str, Any]:
    return {
        "schema_version": "factory-data-v2",
        "items": [
            {"id": "ore", "kind": "item"},
            {"id": "gear", "kind": "item"},
            {"id": "science-pack-a", "kind": "item"},
            {"id": "science-pack-b", "kind": "item"},
        ],
        "recipes": [
            {
                "id": "make-gear",
                "coefficients": {"ore": -1.0, "gear": 1.0},
                "energy_required": 1.0,
                "ingredients": [{"type": "item", "name": "ore", "amount": 1.0}],
                "results": [{"type": "item", "name": "gear", "amount": 1.0}],
                "production_cost": 0.0,
            },
            {
                "id": "make-science-a",
                "coefficients": {"gear": -1.0, "science-pack-a": 1.0},
                "energy_required": 1.0,
                "ingredients": [{"type": "item", "name": "gear", "amount": 1.0}],
                "results": [{"type": "item", "name": "science-pack-a", "amount": 1.0}],
                "production_cost": 0.0,
            },
            {
                "id": "make-science-b",
                "coefficients": {"gear": -1.0, "science-pack-b": 1.0},
                "energy_required": 1.0,
                "ingredients": [{"type": "item", "name": "gear", "amount": 1.0}],
                "results": [{"type": "item", "name": "science-pack-b", "amount": 1.0}],
                "production_cost": 0.0,
            },
        ],
        "final_demands": {"science-pack-a": 1.0},
        "external_supplies": {"ore": {"cost": 1.0, "capacity": 10.0}},
        "unmet_demand_penalty_rate": 1000.0,
        "milestones": [
            {
                "milestone": "science-pack-a",
                "recipe_names": ["make-gear", "make-science-a"],
                "diagnostics": [],
            },
            {
                "milestone": "science-pack-b",
                "recipe_names": [
                    "make-gear",
                    "make-science-a",
                    "make-science-b",
                ],
                "diagnostics": [],
            },
        ],
    }


def _wait_for_job(client: TestClient, job_id: str) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for _ in range(50):
        response = client.get(f"/api/solve/{job_id}")
        assert response.status_code == HTTP_OK
        body = response.json()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(0.05)
    return body


def test_default_problem_endpoint_shape() -> None:
    response = TestClient(app).get("/api/problem/default")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert {
        "package_id",
        "scenario_id",
        "scenario_label",
        "items",
        "demands",
        "target_demands",
        "rate_units",
        "default_solve_mode",
        "external_inputs",
        "raw_input_candidates",
        "recipe_ids",
    } <= set(body)
    assert body["package_id"] == DEFAULT_PACKAGE_ID
    assert body["scenario_id"] == DEFAULT_SCENARIO_ID
    assert (
        body["target_demands"][: len(FIRST_SIX_SCIENCE_TARGETS)]
        == FIRST_SIX_SCIENCE_TARGETS
    )
    assert all("science-pack" in target for target in body["target_demands"])
    assert body["rate_units"] == "items/s"
    assert body["default_solve_mode"] == "hard_demand"
    assert body["item_metadata"] == {}
    assert body["recipe_metadata"] == {}
    assert {"id": "py-science-pack-1", "kind": "item"} in body["items"]


def test_explorer_autoloads_default_and_returns_package_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    app_module.clear_current_package()

    response = TestClient(app).get("/api/explorer")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["package_id"] == DEFAULT_PACKAGE_ID
    assert body["overview"]["item_count"] == len(body["items"])
    assert body["overview"]["fluid_count"] == sum(
        1 for item in body["items"] if item["kind"] == "fluid"
    )
    assert body["overview"]["recipe_count"] == len(body["recipes"])


def test_uploaded_package_updates_current_explorer_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    app_module.clear_current_package()
    client = TestClient(app)

    uploaded = client.post("/api/problem/package", json=_water_package()).json()
    explorer = client.get("/api/explorer")

    assert explorer.status_code == HTTP_OK
    body = explorer.json()
    assert body["package_id"] == uploaded["package_id"]
    assert [item["id"] for item in body["items"]] == ["water"]
    assert [recipe["id"] for recipe in body["recipes"]] == ["pump-water"]
    recipe = body["recipes"][0]
    assert recipe["energy_required"] == 1.0
    assert recipe["source_prototype_type"] == "boiler"
    assert recipe["source_prototype_name"] == "offshore-pumpish-boiler"
    assert recipe["outputs"] == [
        {
            "item_id": "water",
            "kind": "fluid",
            "category": "unknown",
            "amount": 1.0,
            "terms": [
                {
                    "type": "fluid",
                    "name": "water",
                    "amount": 1.0,
                    "amount_min": None,
                    "amount_max": None,
                    "probability": None,
                    "catalyst_amount": None,
                    "temperature": None,
                    "minimum_temperature": None,
                    "maximum_temperature": None,
                    "fluidbox_index": None,
                },
            ],
        },
    ]


def test_solve_edits_do_not_mutate_current_explorer_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    app_module.clear_current_package()
    client = TestClient(app)
    uploaded = client.post(
        "/api/problem/package", json=_water_package(demand=1.0)
    ).json()

    queued = client.post(
        "/api/solve",
        json={
            "package_id": uploaded["package_id"],
            "demands": {"water": 4.0},
            "external_inputs": [],
        },
    )
    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["status"] == "succeeded"

    explorer = client.get("/api/explorer").json()
    assert explorer["package_id"] == uploaded["package_id"]
    assert explorer["items"] == [
        {
            "id": "water",
            "kind": "fluid",
            "category": "unknown",
            "unlock_condition": {"type": "unknown", "id": None},
            "produced_by": [{"id": "pump-water", "category": "unknown"}],
            "consumed_by": [],
        },
    ]


def test_explorer_endpoint_does_not_invoke_solver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    app_module.clear_current_package()

    def fail_solver(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("solver should not run")

    monkeypatch.setattr(app_module, "solve_global_recipe_lp", fail_solver)

    response = TestClient(app).get("/api/explorer")

    assert response.status_code == HTTP_OK


def test_solve_job_eventually_succeeds_for_curated_science_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DEFAULT_DATA_PATH_ENV, str(_curated_default_path()))
    client = TestClient(app)
    problem = client.get("/api/problem/default").json()

    queued = client.post(
        "/api/solve",
        json={
            "demands": {"automation-science-pack": SCIENCE_TEST_RATE},
            "external_inputs": problem["external_inputs"],
        },
    )

    assert queued.status_code == HTTP_OK
    job = queued.json()
    assert job["status"] == "queued"
    assert job["job_id"]

    body = _wait_for_job(client, job["job_id"])
    assert body["status"] == "succeeded"
    assert body["result"]["solver_status"] == "optimal"
    assert body["result"]["objective_value"] is not None
    assert (
        body["result"]["recipe_rates"]["craft-automation-science-pack"]
        == SCIENCE_TEST_RATE
    )
    diagnostics = body["result"]["cluster_diagnostics"]
    assert diagnostics is not None
    assert diagnostics["mode"] == "diagnostic_only"
    assert diagnostics["base_objective_value"] == body["result"]["objective_value"]
    assert diagnostics["clusters"]
    cluster = diagnostics["clusters"][0]
    assert {
        "id",
        "label",
        "category",
        "recipe_ids",
        "active_recipe_count",
        "boundary_item_type_count",
        "boundary_items",
        "diagnostic_components",
    } <= set(cluster)
    if cluster["boundary_items"]:
        boundary_item = cluster["boundary_items"][0]
        assert {
            "item_id",
            "direction",
            "is_zero_net",
            "quantity",
            "flow_cost",
            "port_cost",
        } <= set(boundary_item)
    assert body["result"]["optimized_clustering"] is None


def test_solve_enabled_optimized_clustering_response_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DEFAULT_DATA_PATH_ENV, str(_curated_default_path()))
    client = TestClient(app)
    problem = client.get("/api/problem/default").json()

    queued = client.post(
        "/api/solve",
        json={
            "demands": {"automation-science-pack": SCIENCE_TEST_RATE},
            "external_inputs": problem["external_inputs"],
            "optimized_clustering": {
                "enabled": True,
                "preset": "even_size",
                "reporting_epsilon": 1e-6,
                "time_limit_seconds": 10,
                "max_cluster_size_constraint": "hard",
                "allow_recipe_splitting": False,
                "splittable_recipe_ids": ["automation-science-pack"],
            },
        },
    )

    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    result = body["result"]
    assert result["solver_status"] == "optimal"
    assert result["cluster_diagnostics"]["mode"] == "diagnostic_only"
    optimized = result["optimized_clustering"]
    assert optimized is not None
    assert optimized["status"] in {"optimal", "no_active_recipes", "solver_unavailable"}
    assert optimized["mode"] == "continuous_split"
    assert optimized["effective_parameters"]["preset"] == "even_size"
    assert optimized["effective_parameters"]["allow_recipe_splitting"] is False
    assert optimized["effective_parameters"]["max_cluster_size_constraint"] == "hard"
    assert optimized["effective_parameters"]["splittable_recipe_ids"] == [
        "automation-science-pack",
    ]
    assert "cluster_size_penalty" in optimized["objective_components"]
    assert "cluster_cost" not in optimized["objective_components"]
    optimized_fields = {"clusters", "allocations", "flows", "external_flows"}
    assert optimized_fields | {"reconciliation"} <= set(optimized)
    for row in optimized["external_flows"]:
        assert row["boundary_label"] == "aggregate_external_balance"


def test_solve_rejects_invalid_optimized_clustering_config() -> None:
    client = TestClient(app)
    invalid_configs = [
        {"enabled": True, "reporting_epsilon": 1e-12},
        {"enabled": True, "time_limit_seconds": 601},
        {"enabled": True, "flow_cost_per_quantity": -1},
        {"enabled": True, "min_cluster_size": 5, "max_cluster_size": 4},
        {"enabled": "true"},
        {"enabled": True, "allow_recipe_splitting": "true"},
        {"enabled": True, "max_cluster_size_constraint": "bad"},
        {"enabled": True, "splittable_recipe_ids": ["a", "a"]},
    ]

    for config in invalid_configs:
        response = client.post(
            "/api/solve",
            json={
                "demands": {"automation-science-pack": 1.0},
                "external_inputs": [],
                "optimized_clustering": config,
            },
        )
        assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_solve_rejects_one_sided_optimized_clustering_bounds() -> None:
    client = TestClient(app)

    for config in [
        {"enabled": True, "max_cluster_size": 4},
        {"enabled": True, "min_cluster_size": 20},
    ]:
        response = client.post(
            "/api/solve",
            json={
                "demands": {"automation-science-pack": 1.0},
                "external_inputs": [],
                "optimized_clustering": config,
            },
        )

        assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert "min_cluster_size" in str(response.json()["detail"])


def test_global_lp_failure_omits_optimized_clustering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    client = TestClient(app)
    uploaded = client.post(
        "/api/problem/package",
        json=_unproducible_water_package(demand=UNPRODUCIBLE_WATER_DEMAND),
    ).json()

    queued = client.post(
        "/api/solve",
        json={
            "package_id": uploaded["package_id"],
            "demands": {"water": UNPRODUCIBLE_WATER_DEMAND},
            "external_inputs": [],
            "optimized_clustering": {"enabled": True},
        },
    )

    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["result"]["solver_status"] == "infeasible"
    assert body["result"]["optimized_clustering"] is None


def test_nested_optimized_clustering_failure_preserves_global_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(
        app_module,
        "optimize_clustering",
        lambda *_args, **_kwargs: {
            "status": "model_too_large",
            "mode": "continuous_split",
            "effective_parameters": {
                "enabled": True,
                "mode": "continuous_split",
                "preset": "balanced",
                "preset_is_provisional": False,
                "flow_cost_per_quantity": 1.0,
                "port_cost_per_item_type": 100.0,
                "cluster_size_penalty_weight": 10.0,
                "min_cluster_size": 5.0,
                "max_cluster_size": 15.0,
                "reporting_epsilon": 1e-6,
                "time_limit_seconds": 60.0,
            },
            "objective_value": None,
            "objective_components": {
                "flow_cost": 0.0,
                "port_cost": 0.0,
                "cluster_size_penalty": 0.0,
                "duplication_cost": 0.0,
            },
            "cost_breakdown": {},
            "clusters": [],
            "allocations": [],
            "flows": [],
            "external_flows": [],
            "reconciliation": {
                "objective_total": 0.0,
                "breakdown_total": 0.0,
                "difference": 0.0,
                "reconciled": True,
            },
            "message": "optimized clustering model exceeds guardrail",
            "model_size": {"score": 1, "max_score": 0},
        },
    )
    monkeypatch.setenv(DEFAULT_DATA_PATH_ENV, str(_curated_default_path()))
    client = TestClient(app)
    problem = client.get("/api/problem/default").json()

    queued = client.post(
        "/api/solve",
        json={
            "demands": {"automation-science-pack": 1.0},
            "external_inputs": problem["external_inputs"],
            "optimized_clustering": {"enabled": True},
        },
    )

    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["result"]["solver_status"] == "optimal"
    assert body["result"]["optimized_clustering"]["status"] == "model_too_large"


def test_optimized_clustering_solver_details_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(
        app_module,
        "optimize_clustering",
        lambda *_args, **_kwargs: {
            "status": "solver_unavailable",
            "mode": "continuous_split",
            "effective_parameters": {
                "enabled": True,
                "mode": "continuous_split",
                "preset": "balanced",
                "preset_is_provisional": False,
                "flow_cost_per_quantity": 1.0,
                "port_cost_per_item_type": 100.0,
                "cluster_size_penalty_weight": 10.0,
                "min_cluster_size": 5.0,
                "max_cluster_size": 15.0,
                "reporting_epsilon": 1e-6,
                "time_limit_seconds": 60.0,
            },
            "objective_value": 0.0,
            "objective_components": {
                "flow_cost": 0.0,
                "port_cost": 0.0,
                "cluster_size_penalty": 0.0,
                "duplication_cost": 0.0,
            },
            "cost_breakdown": {},
            "clusters": [],
            "allocations": [],
            "flows": [],
            "external_flows": [],
            "reconciliation": {
                "objective_total": 0.0,
                "breakdown_total": 0.0,
                "difference": 0.0,
                "reconciled": True,
            },
            "message": "HiGHS solver is not available",
            "details": "/home/fungi/local/solver/bin/highs missing",
        },
    )
    monkeypatch.setenv(DEFAULT_DATA_PATH_ENV, str(_curated_default_path()))
    client = TestClient(app)
    problem = client.get("/api/problem/default").json()

    queued = client.post(
        "/api/solve",
        json={
            "demands": {"automation-science-pack": 1.0},
            "external_inputs": problem["external_inputs"],
            "optimized_clustering": {"enabled": True},
        },
    )

    body = _wait_for_job(client, queued.json()["job_id"])
    optimized = body["result"]["optimized_clustering"]
    assert optimized["status"] == "solver_unavailable"
    assert optimized["message"] == "optimized clustering solver is unavailable"
    assert optimized["details"] == ""


def test_default_raw_input_candidates_have_sources() -> None:
    body = TestClient(app).get("/api/problem/default").json()
    candidates = {
        candidate["item_id"]: candidate for candidate in body["raw_input_candidates"]
    }

    assert "coal" not in candidates
    assert {"iron-ore", "copper-ore", "stone"} <= set(candidates)
    for item_id in ["iron-ore", "copper-ore", "stone"]:
        candidate = candidates[item_id]
        assert candidate["source"] == "default_input"
        assert candidate["enabled"] is True
        assert candidate["default_approved"] is True
        assert candidate["capacity"] > 0.0
    if "water" in candidates and candidates["water"]["source"] != "default_input":
        assert candidates["water"]["cost"] == 0.0


def test_default_raw_input_candidates_have_default_caps() -> None:
    body = TestClient(app).get("/api/problem/default").json()

    assert body["raw_input_candidates"]
    implicit_candidates = [
        candidate
        for candidate in body["raw_input_candidates"]
        if candidate["source"] != "default_input"
    ]
    assert all(
        candidate["capacity"] == DEFAULT_EXTERNAL_INPUT_CAPACITY
        for candidate in implicit_candidates
    )
    assert any(
        candidate["kind"] == "fluid" for candidate in body["raw_input_candidates"]
    )


def test_curated_default_package_solves_each_single_science_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DEFAULT_DATA_PATH_ENV, str(_curated_default_path()))
    client = TestClient(app)
    problem = client.get("/api/problem/default").json()

    for target_id in CURATED_SCIENCE_TARGETS:
        queued = client.post(
            "/api/solve",
            json={
                "demands": {target_id: 1.0},
                "external_inputs": problem["external_inputs"],
            },
        )
        assert queued.status_code == HTTP_OK
        body = _wait_for_job(client, queued.json()["job_id"])
        assert body["status"] == "succeeded"
        assert body["result"]["unmet_demand"].get(target_id, 0.0) == 0.0


def test_upload_valid_package_returns_package_id_and_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    response = TestClient(app).post("/api/problem/package", json=_water_package())

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["package_id"]
    assert body["problem"]["package_id"] == body["package_id"]
    assert body["problem"]["scenario_id"] == body["package_id"]
    assert body["problem"]["demands"] == {"water": 2.0}
    assert body["problem"]["target_demands"] == ["water"]
    assert body["problem"]["recipe_ids"] == ["pump-water"]


def test_uploaded_problem_infers_unproduced_raw_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    package = _water_package()
    package["items"] = [
        {"id": "water", "kind": "fluid"},
        {"id": "sand", "kind": "item"},
    ]
    response = TestClient(app).post("/api/problem/package", json=package)

    assert response.status_code == HTTP_OK
    body = response.json()["problem"]
    candidates = {
        candidate["item_id"]: candidate for candidate in body["raw_input_candidates"]
    }
    assert candidates["sand"] == {
        "item_id": "sand",
        "kind": "item",
        "enabled": False,
        "cost": 1.0,
        "capacity": DEFAULT_EXTERNAL_INPUT_CAPACITY,
        "source": "inferred_unproduced",
        "default_approved": False,
    }


def test_uploaded_problem_excludes_coal_when_raw_coal_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    response = TestClient(app).post(
        "/api/problem/package",
        json=_coal_and_raw_coal_package(),
    )

    assert response.status_code == HTTP_OK
    candidates = response.json()["problem"]["raw_input_candidates"]
    candidates = {candidate["item_id"]: candidate for candidate in candidates}
    assert candidates["raw-coal"] == {
        "item_id": "raw-coal",
        "kind": "item",
        "enabled": True,
        "cost": 1.0,
        "capacity": 10.0,
        "source": "default_input",
        "default_approved": True,
    }
    assert "coal" not in candidates


def test_solve_uses_uploaded_package_not_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    client = TestClient(app)
    uploaded = client.post(
        "/api/problem/package",
        json=_water_package(demand=3.0),
    ).json()

    queued = client.post(
        "/api/solve",
        json={
            "package_id": uploaded["package_id"],
            "demands": uploaded["problem"]["demands"],
            "external_inputs": uploaded["problem"]["external_inputs"],
        },
    )

    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["status"] == "succeeded"
    assert body["result"]["recipe_rates"] == {"pump-water": 3.0}


def test_solve_unknown_selected_milestone_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    client = TestClient(app)
    uploaded = client.post(
        "/api/problem/package",
        json=_milestone_filter_package(),
    ).json()

    response = client.post(
        "/api/solve",
        json={
            "package_id": uploaded["package_id"],
            "selected_milestone": "not-a-milestone",
            "demands": {"science-pack-a": 1.0},
            "external_inputs": uploaded["problem"]["external_inputs"],
        },
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "unknown selected milestone" in response.json()["detail"]


def test_solve_selected_milestone_filters_solver_recipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    captured_recipe_ids: list[str] = []

    @dataclass
    class SolverResult:
        status = "optimal"
        objective_value: float = 0.0
        objective_components: dict[str, float] = field(default_factory=dict)
        recipe_rates: dict[str, float] = field(default_factory=dict)
        external_supplies: dict[str, float] = field(default_factory=dict)
        unmet_demand: dict[str, float] = field(default_factory=dict)
        surplus: dict[str, float] = field(default_factory=dict)
        balance_residuals: dict[str, float] = field(default_factory=dict)
        message = ""
        details = ""

    def capture_solver(package: FactoryDataPackage, **_kwargs: object) -> SolverResult:
        captured_recipe_ids.extend(recipe.id for recipe in package.recipes)
        return SolverResult()

    monkeypatch.setattr(app_module, "solve_global_recipe_lp", capture_solver)
    client = TestClient(app)
    uploaded = client.post(
        "/api/problem/package",
        json=_milestone_filter_package(),
    ).json()

    queued = client.post(
        "/api/solve",
        json={
            "package_id": uploaded["package_id"],
            "selected_milestone": "science-pack-a",
            "demands": {"science-pack-a": 1.0},
            "external_inputs": uploaded["problem"]["external_inputs"],
        },
    )

    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["status"] == "succeeded"
    assert captured_recipe_ids == ["make-gear", "make-science-a"]


def test_solve_mode_defaults_to_hard_demand_for_uploaded_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    client = TestClient(app)
    uploaded = client.post(
        "/api/problem/package",
        json=_unproducible_water_package(demand=UNPRODUCIBLE_WATER_DEMAND),
    ).json()

    queued = client.post(
        "/api/solve",
        json={
            "package_id": uploaded["package_id"],
            "demands": {"water": UNPRODUCIBLE_WATER_DEMAND},
            "external_inputs": [],
        },
    )

    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["status"] == "succeeded"
    assert body["result"]["solver_status"] == "infeasible"
    assert body["result"]["objective_value"] is None
    assert body["result"]["unmet_demand"] == {}
    assert body["result"]["cluster_diagnostics"] is None


def test_solve_mode_soft_diagnostics_reports_unmet_demand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    client = TestClient(app)
    uploaded = client.post(
        "/api/problem/package",
        json=_unproducible_water_package(demand=UNPRODUCIBLE_WATER_DEMAND),
    ).json()

    queued = client.post(
        "/api/solve",
        json={
            "package_id": uploaded["package_id"],
            "solve_mode": "soft_diagnostics",
            "demands": {"water": UNPRODUCIBLE_WATER_DEMAND},
            "external_inputs": [],
        },
    )

    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["status"] == "succeeded"
    assert body["result"]["solver_status"] == "optimal"
    assert body["result"]["unmet_demand"]["water"] == UNPRODUCIBLE_WATER_DEMAND
    assert body["result"]["cluster_diagnostics"] is not None
    assert (
        body["result"]["objective_components"]["unmet_demand_penalty"]
        == UNPRODUCIBLE_WATER_PENALTY
    )


def test_result_to_dto_accepts_missing_cluster_diagnostics() -> None:
    @dataclass
    class SolverResult:
        status = "optimal"
        objective_value: float = 0.0
        objective_components: dict[str, float] = field(default_factory=dict)
        recipe_rates: dict[str, float] = field(default_factory=dict)
        external_supplies: dict[str, float] = field(default_factory=dict)
        unmet_demand: dict[str, float] = field(default_factory=dict)
        surplus: dict[str, float] = field(default_factory=dict)
        balance_residuals: dict[str, float] = field(default_factory=dict)
        message = ""
        details = ""

    dto = result_to_dto(SolverResult())  # type: ignore[arg-type]

    assert dto.cluster_diagnostics is None
    assert '"cluster_diagnostics":null' in dto.model_dump_json()


def test_solve_rejects_invalid_solve_mode() -> None:
    response = TestClient(app).post(
        "/api/solve",
        json={
            "solve_mode": "diagnose",
            "demands": {"automation-science-pack": 1.0},
            "external_inputs": [],
        },
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_solve_without_package_id_remains_default_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DEFAULT_DATA_PATH_ENV, str(_curated_default_path()))
    client = TestClient(app)
    problem = client.get("/api/problem/default").json()
    queued = client.post(
        "/api/solve",
        json={
            "demands": {"automation-science-pack": 1.0},
            "external_inputs": problem["external_inputs"],
        },
    )

    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["status"] == "succeeded"
    assert "craft-automation-science-pack" in body["result"]["recipe_rates"]


def test_solve_accepts_default_package_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEFAULT_DATA_PATH_ENV, str(_curated_default_path()))
    client = TestClient(app)
    problem = client.get("/api/problem/default").json()

    queued = client.post(
        "/api/solve",
        json={
            "package_id": problem["package_id"],
            "demands": {"automation-science-pack": 1.0},
            "external_inputs": problem["external_inputs"],
        },
    )

    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["status"] == "succeeded"
    assert "craft-automation-science-pack" in body["result"]["recipe_rates"]


def test_solve_unknown_package_id_returns_404() -> None:
    response = TestClient(app).post(
        "/api/solve",
        json={"package_id": "not-a-package", "demands": {}, "external_inputs": []},
    )

    assert response.status_code == HTTP_NOT_FOUND


def test_upload_invalid_package_returns_422() -> None:
    response = TestClient(app).post(
        "/api/problem/package",
        json={"schema_version": "factory-data-v1"},
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_upload_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "MAX_PACKAGE_UPLOAD_BYTES", 4)

    response = TestClient(app).post("/api/problem/package", content=b"12345")

    assert response.status_code == HTTP_PAYLOAD_TOO_LARGE


def test_upload_rejects_when_package_store_is_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")
    monkeypatch.setattr(app_module, "MAX_STORED_PACKAGES", 1)
    monkeypatch.setattr(app_module, "uploaded_packages", {})
    client = TestClient(app)

    first = client.post("/api/problem/package", json=_water_package())
    second = client.post("/api/problem/package", json=_water_package())

    assert first.status_code == HTTP_OK
    assert second.status_code == HTTP_TOO_MANY_REQUESTS


def test_unknown_job_returns_404() -> None:
    response = TestClient(app).get("/api/solve/not-a-job")

    assert response.status_code == HTTP_NOT_FOUND


def test_solve_returns_429_when_job_store_is_saturated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_module = import_module("factory_plan_api.app")

    class FullJobStore:
        def submit(self, _solve: object) -> object:
            raise SolveJobStoreFullError("too many queued or running solve jobs")

    monkeypatch.setattr(app_module, "job_store", FullJobStore())

    response = TestClient(app).post(
        "/api/solve",
        json={"demands": {"automation-science-pack": 1.0}, "external_inputs": []},
    )

    assert response.status_code == HTTP_TOO_MANY_REQUESTS
    assert "too many" in response.json()["detail"]


def test_default_resolver_works_from_non_root_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    package = load_default_factory_data()

    assert set(CURATED_SCIENCE_TARGETS) <= {item.id for item in package.items}


def test_default_resolver_prefers_generated_real_package_when_present() -> None:
    path = default_data_path()

    assert path.as_posix().endswith(GENERATED_DEFAULT_RELATIVE_PATH.as_posix())


def test_default_resolver_falls_back_to_toy_when_generated_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_exists = Path.exists

    def exists_without_generated(path: Path) -> bool:
        if path.as_posix().endswith(GENERATED_DEFAULT_RELATIVE_PATH.as_posix()):
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists_without_generated)

    path = default_data_path()

    assert path.as_posix().endswith("examples/data/toy_iron.factory-data.json")


def test_default_loader_falls_back_when_generated_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_text = Path.read_text

    def read_stale_generated(path: Path, encoding: str | None = None) -> str:
        if path.as_posix().endswith(GENERATED_DEFAULT_RELATIVE_PATH.as_posix()):
            return '{"schema_version": "factory-data-v1"}'
        return original_read_text(path, encoding=encoding)

    monkeypatch.delenv(DEFAULT_DATA_PATH_ENV, raising=False)
    monkeypatch.setattr(Path, "read_text", read_stale_generated)

    package = load_default_factory_data()

    assert package.schema_version == "factory-data-v2"


def test_default_resolver_uses_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "override.factory-data.json"
    package_path.write_text(
        """
        {
          "schema_version": "factory-data-v2",
          "items": [{"id": "water", "kind": "fluid"}],
          "recipes": [
            {
              "id": "vent-water",
              "coefficients": {"water": 1.0},
              "energy_required": 1.0,
              "ingredients": [],
              "results": [{"type": "fluid", "name": "water", "amount": 1.0}],
              "production_cost": 0.0
            }
          ],
          "final_demands": {"water": 2.0},
          "external_supplies": {},
          "unmet_demand_penalty_rate": 1.0
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv(DEFAULT_DATA_PATH_ENV, str(package_path))

    package = load_default_factory_data()

    assert package.final_demands == {"water": 2.0}


def test_solve_rejects_negative_demands() -> None:
    response = TestClient(app).post(
        "/api/solve",
        json={"demands": {"automation-science-pack": -1.0}, "external_inputs": []},
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "nonnegative" in str(response.json())


def test_solve_rejects_unknown_demand_item_id() -> None:
    response = TestClient(app).post(
        "/api/solve",
        json={"demands": {"copper-gear": 1.0}, "external_inputs": []},
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "unknown demand item" in response.json()["detail"]


def test_solve_rejects_unknown_external_input_item_id() -> None:
    response = TestClient(app).post(
        "/api/solve",
        json={
            "demands": {"automation-science-pack": 1.0},
            "external_inputs": [
                {"item_id": "not-a-real-item-id", "enabled": True, "cost": 1.0},
            ],
        },
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "unknown external input" in response.json()["detail"]


def test_solve_rejects_duplicate_external_input_entries() -> None:
    response = TestClient(app).post(
        "/api/solve",
        json={
            "demands": {"automation-science-pack": 1.0},
            "external_inputs": [
                {"item_id": "iron-ore", "enabled": True, "cost": 1.0},
                {"item_id": "iron-ore", "enabled": True, "cost": 2.0},
            ],
        },
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "duplicate" in str(response.json())
