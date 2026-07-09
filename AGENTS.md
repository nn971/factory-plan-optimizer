# AGENTS.md

## Repo shape

- `uv` workspace members are `backend/api`, `backend/game-data-extractor`, and `backend/optimizer-core`; run Python checks from the package directory, not the repo root.
- Architecture boundary: `frontend` talks only to `backend/api` over HTTP; `backend/api` imports optimizer-core and public extractor contracts only; optimizer core must not import API/frontend code.
- `backend/game-data-extractor` owns importer workflows and the `game-data-extractor` CLI. It must not depend on or import `factory_plan_optimizer`, `pyomo`, or `highspy`.
- Optimizer-core and API may import `game_data_extractor.data_contracts` but must not import extractor workflow modules.
- `FactoryDataPackage` is the canonical optimizer-facing data contract, owned by `game_data_extractor.data_contracts`; importers/generators may be richer, but optimizer modules consume the package shape documented in `docs/data_interface.md`.

## Commands

- Optimizer core checks:
  ```bash
  cd backend/optimizer-core
  uv run python -m pytest
  uv run python -m ruff check src tests
  uv run python -m ruff format --check src tests
  uv run python -m mypy src
  ```
- Game data extractor checks:
  ```bash
  cd backend/game-data-extractor
  uv run python -m pytest
  uv run python -m ruff check src tests
  uv run python -m ruff format --check src tests
  uv run python -m mypy src
  ```
- API checks:
  ```bash
  cd backend/api
  uv run python -m pytest
  uv run python -m ruff check src tests
  uv run python -m ruff format --check src tests
  uv run python -m mypy src
  ```
- Frontend checks:
  ```bash
  cd frontend
  npm run build
  npm run check:boundaries
  ```
- Workspace sanity check from repo root: `uv lock --dry-run`.
- API dev server: `cd backend/api && uv run uvicorn factory_plan_api.app:app --reload`.
- Frontend dev server: `cd frontend && npm run dev`; Vite proxies `/api` to `http://127.0.0.1:8000`. For preview/separate hosting, set `VITE_API_BASE_URL`.
- Focused tests use normal pytest paths, e.g. `cd backend/optimizer-core && uv run python -m pytest tests/test_global_recipe_lp.py`.

## Modeling and solver conventions

- Use Python 3.12+, Pyomo for symbolic optimization models, and HiGHS as the default open-source solver.
- Recipe coefficients are signed net production `a_ir`: positive outputs, negative inputs.
- TURD recipes are Pyanodon-specific and should not get special-case code or predicates. Treat them like any other recipe according to normal enabled/unlock/milestone data; if they are disabled by default, doing nothing special is correct.
- Global balance convention: `sum_r a_ir * x_r + external_supply_i = final_demand_i`; current LP implementation includes explicit `unmet_demand_i` and `surplus_i` diagnostics as documented in `docs/mathematical_model.md`.
- Always report objective components by name: `raw_cost`, `production_cost`, `flow_cost`, `port_cost`, `cluster_cost`, `duplication_cost`, `unmet_demand_penalty`.
- Do not silently accept infeasible, unbounded, solver-unavailable, or non-optimal statuses; return a structured failure/result or raise a clear exception as the surrounding module expects.
- Result objects should be straightforward to serialize to JSON for comparison.

## Scope and data gotchas

- This repo is an abstract optimizer/testing UI, not blueprint generation; do not add neural nets, exact tile layout, train scheduling, spoilage, or GUI-heavy features unless explicitly requested.
- Keep examples under `examples/` small enough to verify by hand; `examples/data/toy_iron.factory-data.json` is the first canonical package.
- Importer workflow writes generated artifacts under `data/generated/`; do not commit real saves, mod zips, full `data.raw` dumps, or generated large datasets. `.omo/` is reserved for agent scratch state.
- Importer workflow commands live on `game-data-extractor`; `dump-data` currently supports only `--dry-run`, and non-dry-run intentionally returns `factorio_dump_unavailable` until a real isolated Factorio settings workflow exists.

## Frontend/API specifics

- Main API endpoints are `GET /api/problem/default`, `POST /api/solve`, and `GET /api/solve/{job_id}`.
- Solve jobs are in-memory, bounded, and intended for local testing rather than durable production job management.
- Frontend boundary check rejects references to Python/backend paths from `frontend/src`; keep DTO/API interaction in `frontend/src/api`.

## Documentation expectations

- Every new optimization model needs a matching explanation in `docs/mathematical_model.md`.
- Every nontrivial heuristic should document its input, output, approximated objective, known failure modes, and test examples.
