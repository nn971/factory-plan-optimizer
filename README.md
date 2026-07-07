# Factory Plan Optimizer

Experimental scaffold for a hierarchical Factorio-style factory-planning optimizer.

The repository is now split into a small web UI and a Python backend:

```text
frontend/                 Vite + React + TypeScript testing UI
backend/api/              FastAPI boundary used by the UI
backend/optimizer-core/   Python optimizer package: factory_plan_optimizer
```

The frontend talks only to the HTTP API. The optimizer core does not import the
API or frontend. The API is the integration layer and imports optimizer-core as a
Python package.

## Development setup

Python packages are managed as a `uv` workspace from the repository root.

### Optimizer core

```bash
cd backend/optimizer-core
uv run python -m pytest
uv run python -m ruff check src tests
uv run python -m ruff format --check src tests
uv run python -m mypy src
```

### API server

```bash
cd backend/api
uv run uvicorn factory_plan_api.app:app --reload
```

API checks:

```bash
cd backend/api
uv run python -m pytest
uv run python -m ruff check src tests
uv run python -m ruff format --check src tests
uv run python -m mypy src
```

Main endpoints:

- `GET /api/problem/default`
- `POST /api/solve`
- `GET /api/solve/{job_id}`

Solver jobs are in-memory and bounded. They are intended for local testing, not
durable production job management.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend checks:

```bash
cd frontend
npm run build
npm run check:boundaries
```

`vite dev` proxies `/api` to `http://127.0.0.1:8000`. For preview builds,
Electron, Tauri, or a separately hosted API, set:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

If frontend and API are not served from the same origin or through the Vite dev
proxy, API CORS configuration may be needed in a future task.

## UI scope

The current UI is a minimal testing dashboard. It can:

- load the default toy problem;
- edit demand amounts;
- enable/disable external inputs;
- adjust input cost and optional capacity;
- start an async solver job;
- poll job status;
- display objective components, recipe rates, supplies, unmet demand, surplus,
  and residuals.

It intentionally has no routing, no global state framework, and no advanced
visualization yet.

## Workspace validation

From the repository root:

```bash
uv lock --dry-run
```

Run package-specific checks from each package directory as shown above.
