from __future__ import annotations

import time
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.testclient import TestClient

from factory_plan_api.app import app
from factory_plan_api.default_data import (
    DEFAULT_DATA_PATH_ENV,
    default_data_path,
    load_default_factory_data,
)
from factory_plan_api.jobs import SolveJobStoreFullError

if TYPE_CHECKING:
    import pytest

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_PAYLOAD_TOO_LARGE = 413
HTTP_TOO_MANY_REQUESTS = 429
HTTP_UNPROCESSABLE_ENTITY = 422
EXPECTED_GEAR_RATE = 5.0


def _water_package(demand: float = 2.0) -> dict[str, Any]:
    return {
        "schema_version": "factory-data-v1",
        "items": [{"id": "water", "kind": "fluid"}],
        "recipes": [
            {
                "id": "pump-water",
                "coefficients": {"water": 1.0},
                "production_cost": 0.0,
            },
        ],
        "final_demands": {"water": demand},
        "external_supplies": {},
        "unmet_demand_penalty_rate": 1000.0,
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
    assert {"items", "demands", "external_inputs", "recipe_ids"} <= set(body)
    assert {"id": "iron-gear", "kind": "item"} in body["items"]
    assert body["demands"] == {"iron-gear": 5.0}
    iron_ore_input = next(
        option for option in body["external_inputs"] if option["item_id"] == "iron-ore"
    )
    assert iron_ore_input["enabled"] is True
    assert iron_ore_input["cost"] == 1.0


def test_solve_job_eventually_succeeds_for_toy_request() -> None:
    client = TestClient(app)
    problem = client.get("/api/problem/default").json()

    queued = client.post(
        "/api/solve",
        json={
            "demands": problem["demands"],
            "external_inputs": problem["external_inputs"],
        },
    )

    assert queued.status_code == HTTP_OK
    job = queued.json()
    assert job["status"] == "queued"
    assert job["job_id"]

    latest = None
    for _ in range(50):
        latest = client.get(f"/api/solve/{job['job_id']}")
        assert latest.status_code == HTTP_OK
        body = latest.json()
        if body["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)

    assert latest is not None
    body = latest.json()
    assert body["status"] == "succeeded"
    assert body["result"]["solver_status"] == "optimal"
    assert body["result"]["objective_value"] is not None
    assert body["result"]["recipe_rates"]["make-gear"] == EXPECTED_GEAR_RATE


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
    assert body["problem"]["demands"] == {"water": 2.0}
    assert body["problem"]["recipe_ids"] == ["pump-water"]


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


def test_solve_without_package_id_remains_default_compatible() -> None:
    client = TestClient(app)
    queued = client.post(
        "/api/solve",
        json={"demands": {"iron-gear": 1.0}, "external_inputs": []},
    )

    assert queued.status_code == HTTP_OK
    body = _wait_for_job(client, queued.json()["job_id"])
    assert body["status"] == "succeeded"
    assert "make-gear" in body["result"]["recipe_rates"]


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
        json={"demands": {"iron-gear": 1.0}, "external_inputs": []},
    )

    assert response.status_code == HTTP_TOO_MANY_REQUESTS
    assert "too many" in response.json()["detail"]


def test_default_resolver_works_from_non_root_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    package = load_default_factory_data()

    assert package.final_demands == {"iron-gear": 5.0}


def test_default_resolver_prefers_curated_root_package() -> None:
    path = default_data_path()

    assert path.as_posix().endswith("data/packages/default.factory-data.json")


def test_default_resolver_falls_back_to_toy_when_curated_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_exists = Path.exists

    def exists_without_curated(path: Path) -> bool:
        if path.as_posix().endswith("data/packages/default.factory-data.json"):
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists_without_curated)

    path = default_data_path()

    assert path.as_posix().endswith("examples/data/toy_iron.factory-data.json")


def test_default_resolver_uses_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "override.factory-data.json"
    package_path.write_text(
        """
        {
          "schema_version": "factory-data-v1",
          "items": [{"id": "water", "kind": "fluid"}],
          "recipes": [
            {
              "id": "vent-water",
              "coefficients": {"water": 1.0},
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
        json={"demands": {"iron-gear": -1.0}, "external_inputs": []},
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
            "demands": {"iron-gear": 1.0},
            "external_inputs": [
                {"item_id": "copper-ore", "enabled": True, "cost": 1.0},
            ],
        },
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "unknown external input" in response.json()["detail"]


def test_solve_rejects_duplicate_external_input_entries() -> None:
    response = TestClient(app).post(
        "/api/solve",
        json={
            "demands": {"iron-gear": 1.0},
            "external_inputs": [
                {"item_id": "iron-ore", "enabled": True, "cost": 1.0},
                {"item_id": "iron-ore", "enabled": True, "cost": 2.0},
            ],
        },
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "duplicate" in str(response.json())
