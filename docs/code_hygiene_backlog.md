# Code hygiene backlog

Decision record: `docs/code-hygiene-decisions.md`.

Collected after the practical clustering milestone. This is an interview/triage backlog, not an implementation plan. Each item should be reviewed before changing behavior.

Priority meanings:

- **P1:** likely to hide failures or block the next clustering/visualization work.
- **P2:** drift/maintenance risk that should be settled while APIs and models are still small.
- **P3:** polish or clarity issue; fix when touching nearby code.
- **P4:** low-risk cleanup or observability improvement.

## Clustering strategy cleanup

### P1: Decide the fate of `exact-small`

- **Category:** legacy strategy residue / incomplete mode cleanup
- **Evidence:**
  - `backend/optimizer-core/src/factory_plan_optimizer/optimizer/sparse_clustering.py:28,76,155-160` keeps `SparseClusteringMode` value `"exact-small"`, but dispatch returns `status="unsupported"` with message `"exact-small sparse clustering is not supported in the MVP"`.
  - `backend/api/src/factory_plan_api/dtos.py:184,382` exposes `mode: Literal["fast", "balanced", "exact-small"]` in API-facing DTOs.
  - `backend/api/tests/test_api.py:556-574` and `backend/optimizer-core/tests/test_sparse_clustering.py:276-303` lock in unsupported-mode behavior.
  - `docs/sparse_graph_clustering.md:9,85,124` documents the old strongest-edge strategy as obsolete and notes `exact-small` is unsupported.
- **Question for interview:** remove `exact-small` completely, or retain it as an explicitly deprecated compatibility value?
- **Likely treatment:**
  - If removing: trim mode literals in optimizer/API/DTO/tests/docs.
  - If retaining: mark as deprecated compatibility, keep one narrow contract test, and avoid surrounding dead scaffolding.

### P2: Remove or justify sparse clustering fallback fields

- **Category:** ad-hoc compatibility residue
- **Evidence:** `backend/optimizer-core/src/factory_plan_optimizer/optimizer/sparse_clustering.py:185-186,254-257` has `fallback_attempted`, `fallback_mode`, and `_fallback_compat(...)` that currently remain no-op/defaults.
- **Question for interview:** is a real fallback path planned soon?
- **Likely treatment:** remove result fields and helper until needed, or implement/report real fallback transitions.

### P2: Centralize sparse clustering defaults

- **Category:** hard-coded parameter duplication / drift risk
- **Evidence:**
  - `backend/optimizer-core/src/factory_plan_optimizer/optimizer/sparse_partition.py:48-54` defines `ObjectiveWeights` defaults.
  - `backend/optimizer-core/src/factory_plan_optimizer/optimizer/sparse_clustering.py:38-46,59,67` has inlined mode/runtime/penalty/cap defaults.
  - `frontend/src/domain/problemState.ts:56-86` duplicates frontend default clustering settings.
- **Question for interview:** should defaults live in optimizer-core, API DTO constants, or an explicit config contract surfaced to the frontend?
- **Likely treatment:** create a single source of truth for default values and add contract tests for API/frontend alignment.

### P2: Clarify objective component naming across clustering models

- **Category:** semantic drift / user-facing ambiguity
- **Evidence:**
  - `backend/optimizer-core/src/factory_plan_optimizer/optimizer/cluster_diagnostics.py` and `global_recipe_lp.py` use `cluster_cost`.
  - `frontend/src/domain/solveOutcome.ts:18-47` and `frontend/src/api/dtos.ts:258-263` render backend-defined objective keys flexibly, so inconsistent keys leak to users.
- **Question for interview:** should these terms intentionally represent different concepts, or should the public contract converge?
- **Likely treatment:** document separate meanings clearly or normalize names in DTOs/UI.

### P3: Make inactive LP cluster logistics terms self-explanatory

- **Category:** interface consistency / future misread risk
- **Evidence:** `backend/optimizer-core/src/factory_plan_optimizer/optimizer/global_recipe_lp.py:41-49,158-219` keeps objective component keys for `flow_cost`, `port_cost`, `cluster_cost`, and `duplication_cost`, but these are currently inactive/zero in the global LP while sparse diagnostics report related concepts separately.
- **Question for interview:** should LP objective shape remain stable even when components are inactive?
- **Likely treatment:** keep if intentional, but add comments/docs near `OBJECTIVE_COMPONENT_KEYS` explaining inactive components.

## Graph and cluster visualization

### P1: Replace fixed-column graph layout before expanding cluster UX

- **Category:** hard-coded layout / does not fit clustering
- **Evidence:**
  - `frontend/src/ui/solve-result/FlowGraph.tsx:14-20` defines fixed `GRAPH_WIDTH`, `COLUMN_GAP`, `LEFT_PAD`, `TOP_PAD`, `ROW_GAP`, and `NODE_RADIUS`.
  - `frontend/src/ui/solve-result/FlowGraph.tsx:191-207` lays out nodes by fixed columns (`external`, `item`, `recipe/cluster`, diagnostics) rather than graph structure or clusters.
- **Question for interview:** should the next visualization show raw LP flow, cluster-aware layout, or both as switchable modes?
- **Likely treatment:** compute adaptive bounds/viewBox, dynamic spacing, and cluster-aware grouping before adding more visual detail.

### P1: Stop inferring visual clusters independently from optimizer clustering

- **Category:** source-of-truth mismatch
- **Evidence:**
  - `frontend/src/domain/solveResultFlow.ts:102-107,202-217` infers clusters with connected components and frontend thresholds rather than using sparse/optimized cluster assignments.
  - `frontend/src/domain/solveResultFlow.ts:203-217` hides clustering behind `MIN_CLUSTER_NODE_COUNT=7` and `MIN_GRAPH_NODE_COUNT_FOR_CLUSTERING=13`.
  - `frontend/src/domain/solveResultFlow.ts:185-193` collapses nodes/edges in ways that can obscure original bipartite flow topology.
- **Question for interview:** should frontend heuristic clustering survive as a separate “visual grouping” feature, or be replaced by optimizer-provided cluster IDs?
- **Likely treatment:** add explicit graph modes: raw LP flow, heuristic connected-component grouping, and optimizer/sparse cluster overlay when data is available.

### P2: Avoid recomputing graph details per selection

- **Category:** performance / consistency
- **Evidence:** `frontend/src/domain/solveResultFlow.ts:239-263` rebuilds/recomputes cluster details for each selection.
- **Question for interview:** will graph sizes remain small enough for recompute-on-selection?
- **Likely treatment:** precompute graph/cluster detail indexes when building the solve result view model.

### P2: Reduce fragmented cluster interpretation surfaces

- **Category:** over-abstraction / UX confusion
- **Evidence:**
  - `frontend/src/ui/solve-result/SolveResultPanel.tsx:80-84` makes successful sparse clustering swap out deterministic cluster diagnostics.
  - `frontend/src/ui/solve-result/ClusterDiagnosticsPanel.tsx:24-34` labels diagnostics as “diagnostic only,” while optimized/sparse panels use different objective assumptions.
  - `frontend/src/domain/sparseClustering.ts:51-90`, `SparseClusteringPanel.tsx`, and `SparseBoundaryItemReviewPanel.tsx` create multiple cluster-specific interpretation surfaces, some visible only for sparse success.
- **Question for interview:** what is the intended hierarchy between deterministic diagnostics and sparse post-process explanation?
- **Likely treatment:** add a short section intro linking each panel to its source-of-truth stage, or consolidate panels around one cluster result model.

### P2: Reconsider graph availability gating

- **Category:** ad-hoc bypass / avoidable empty state
- **Evidence:**
  - `frontend/src/ui/solve-result/SolveResultPanel.tsx:35-40` blocks graph rendering unless explorer data availability is successful.
  - `frontend/src/domain/solveOutcome.ts:74-95` treats package/explorer mismatch or stale marker as warning/unavailable states.
- **Question for interview:** can the graph render partial/raw solve data without explorer enrichment?
- **Likely treatment:** degrade gracefully: render raw IDs when explorer labels are unavailable, and show enrichment warnings separately.

## API and failure reporting

### P1: Replace broad sparse clustering exception swallow

- **Category:** ad-hoc bypass / silent failure
- **Evidence:** `backend/api/src/factory_plan_api/app.py:143-189` catches broad `Exception` around sparse clustering and returns generic `{"status": "failed", "message": "sparse clustering failed"}`.
- **Question for interview:** which failures should be recoverable sparse-clustering failures vs whole-job failures?
- **Likely treatment:** catch known expected exceptions, preserve reason codes/details in the sparse clustering payload, and let unexpected exceptions surface through structured job failure handling.

### P3: Add meaning to empty exception subclass

- **Category:** low-risk stub / maintainability
- **Evidence:** `backend/api/src/factory_plan_api/jobs.py:117` declares `SolveJobStoreFullError` with `pass`.
- **Question for interview:** is the type-only exception enough?
- **Likely treatment:** add a docstring, message, or payload if operational clarity is useful; otherwise leave as a typed sentinel.

## Configuration, paths, and constants

### P2: Avoid repo-root discovery by fixed parent depth

- **Category:** hard-coded path / brittle packaging
- **Evidence:** `backend/api/src/factory_plan_api/default_data.py:24,43` uses `Path(__file__).resolve().parents[4]` and duplicates traversal logic.
- **Question for interview:** should default data be resolved as package resources, environment-configured files, or repo-local dev fallback only?
- **Likely treatment:** resolve root once, prefer `FACTORY_PLAN_DEFAULT_DATA_PATH`/package resource, and isolate repo-layout fallback behind a named helper.

### P2: Centralize API and problem defaults

- **Category:** duplicated config / brittle tests
- **Evidence:**
  - `backend/api/src/factory_plan_api/app.py:43-44` hard-codes `MAX_PACKAGE_UPLOAD_BYTES` and `MAX_STORED_PACKAGES`.
  - `backend/api/src/factory_plan_api/problem.py:35-36,59` hard-codes default package/scenario IDs and fallback labels.
  - `backend/api/tests/test_api.py:30-31` redefines the same default IDs.
- **Question for interview:** are these product constants, test fixtures, or deployment config?
- **Likely treatment:** centralize in named constants/config and import those in tests or expose via fixtures.

### P3: Make frontend numeric parsing fail visibly

- **Category:** ad-hoc input coercion / data quality
- **Evidence:** `frontend/src/domain/problemState.ts:61-85,242-256` uses magic string/numeric defaults and parsing helpers that silently coerce invalid values to `0`.
- **Question for interview:** should invalid numeric settings be accepted and normalized, or produce field-level validation errors?
- **Likely treatment:** return validation errors from edit-time parsing; only serialize valid values into solve requests.

### P4: Surface solver/reporting guardrails for reproducibility

- **Category:** hard-coded thresholds / observability
- **Evidence:** `backend/optimizer-core/src/factory_plan_optimizer/optimizer/sparse_clustering.py:38-46,59` includes hard-coded epsilons, runtime limits, caps, and guardrails.
- **Question for interview:** should users see which guardrails affected a solve?
- **Likely treatment:** move to named config constants and include effective limits in diagnostics/results where relevant.

## Suggested interview order

1. Pick `exact-small` policy: remove vs deprecated compatibility.
2. Define clustering source of truth for visualization: raw flow vs heuristic visual grouping vs optimizer cluster IDs.
3. Decide where clustering defaults and objective names should be canonical.
4. Decide failure-reporting contract for sparse clustering.
5. Sweep lower-risk constant/path/input-validation cleanup while touching nearby files.
