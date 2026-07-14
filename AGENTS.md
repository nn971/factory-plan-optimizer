# AGENTS.md

## Repo shape and boundaries

- `uv` workspace members are `backend/api`, `backend/game-data-extractor`, and `backend/optimizer-core`; run Python checks from the package directory, not the repo root.
- `frontend` talks only to `backend/api` over HTTP. Keep DTO/API interaction in `frontend/src/api`; `npm run check:boundaries` rejects Python/backend references from `frontend/src`.
- `backend/api` is the integration layer: imports optimizer-core plus public extractor contracts only; app entrypoint is `factory_plan_api.app:app`.
- `backend/optimizer-core` provides `factory-plan-optimizer`; it may import `game_data_extractor.data_contracts` but must not import API/frontend code or extractor workflow modules.
- `backend/game-data-extractor` owns importer workflows and `game-data-extractor`; it must not import `factory_plan_optimizer`, `pyomo`, or `highspy`.
- `FactoryDataPackage` from `game_data_extractor.data_contracts` is the optimizer/API data contract; keep optimizer inputs aligned with `docs/data_interface.md`.

## Commands to run from the right directory

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
  npm run test
  npm run build
  npm run check:boundaries
  ```
- Workspace sanity check from repo root: `uv lock --dry-run`.
- API dev server: `cd backend/api && uv run uvicorn factory_plan_api.app:app --reload`.
- Frontend dev server: `cd frontend && npm run dev`; Vite proxies `/api` to `http://127.0.0.1:8000`. For preview/separate hosting, set `VITE_API_BASE_URL`.
- Focused tests use normal pytest paths, e.g. `cd backend/optimizer-core && uv run python -m pytest tests/test_global_recipe_lp.py`; frontend focused tests use `cd frontend && npm run test -- <pattern>`.
- CLI entrypoints: `cd backend/game-data-extractor && uv run game-data-extractor --help`; `cd backend/optimizer-core && uv run factory-plan-optimizer plan --help`.

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
- Correct Pyanodon milestone order is: Automation -> py1 -> logistics -> military -> py2 -> chemical -> py3 -> production -> py4 -> utility -> space.
- Keep examples under `examples/` small enough to verify by hand; `examples/data/toy_iron.factory-data.json` is the first canonical package.
- Importer workflow writes reproducible artifacts under `data/generated/` from `data/raw/default-data-raw-dump.json`; use `data/README.md` for regeneration commands.
- Do not commit real saves, mod zips, full `data.raw` dumps, or generated large datasets. `.omo/` is reserved for agent scratch state.
- Importer workflow commands live on `game-data-extractor`; `dump-data` currently supports only `--dry-run`, and non-dry-run intentionally returns `factorio_dump_unavailable` until a real isolated Factorio settings workflow exists.
- API default data uses `FACTORY_PLAN_DEFAULT_DATA_PATH` if set, otherwise `data/generated/default.factory-data.json`, then `examples/data/toy_iron.factory-data.json`; stale generated defaults can be ignored locally and fall back to the toy package.

## Frontend/API specifics

- Main API endpoints are `GET /api/problem/default`, `POST /api/problem/package`, `GET /api/explorer`, `POST /api/solve`, and `GET /api/solve/{job_id}`.
- Solve jobs are in-memory and bounded (`max_workers=2`, `max_active_jobs=8`, `max_retained_jobs=64`); do not treat them as durable production jobs.
- Uploaded problem packages are intentionally limited (1 MB payload, 8 retained packages).

## Documentation expectations

- Every new optimization model needs a matching explanation in `docs/mathematical_model.md`.
- Every nontrivial heuristic should document its input, output, approximated objective, known failure modes, and test examples.
