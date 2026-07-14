# Code Hygiene Decisions

This document records the accepted decisions for treating the issues collected in `docs/code_hygiene_backlog.md` after the practical clustering milestone. It is the contract reference for implementation; the backlog remains the evidence register.

Implementation order:

1. clustering contract cleanup;
2. visualization;
3. general config/input polish.

## Contract matrix

| Contract area | Current state | Target state | Compatibility policy | Tests | Phase |
| --- | --- | --- | --- | --- | --- |
| Sparse clustering modes | `fast`, `balanced`, and `exact-small` are exposed in optimizer/API/frontend; `exact-small` returns unsupported. | Only `fast` and `balanced` are public modes. | Remove `exact-small`; do not preserve an unsupported compatibility mode. Requests using removed mode must fail normal DTO validation. | Update optimizer, API, frontend DTO/UI, and docs tests that currently assert `exact-small` behavior. | 1A |
| Sparse result fallback fields | Sparse results include no-op fallback fields/helpers such as `fallback_attempted`, `fallback_mode`, and compatibility fallback data. | No fallback fields are emitted unless a real fallback path exists. | Remove no-op fields/helpers rather than reserving unused contract surface. | Serialization/DTO tests should assert fallback fields are absent. | 1A |
| Sparse `unsupported` status | `unsupported` is currently used for `exact-small`. Other skip/failure statuses exist for normal guardrails. | Removing `exact-small` removes that unsupported path. Keep status values only for real known states that remain reachable after cleanup. | Do not keep `unsupported` solely for removed `exact-small`; if another real unsupported condition exists, keep it with a reason code. | Update sparse clustering tests around supported modes, skipped/failed paths, and removed unsupported-mode assertions. | 1A, 1D |
| Failure reporting shape | API catches broad sparse clustering exceptions and can return generic `sparse clustering failed`; failure details are inconsistent. | Known clustering limitations/failures use `status`, `reason_code`, `message`, and optional `details`. Unexpected exceptions fail the solve job visibly. | No generic catch-all payload for unexpected clustering exceptions. Known recoverable conditions remain structured in clustering result payloads. | API tests for known structured failures and unexpected exception behavior; optimizer tests for known status payloads. | 1D |
| Failure reason placement | Result status/message exists, but no consistent `reason_code` contract. | Every non-success sparse clustering result includes `reason_code`; successful results omit it. | Use deterministic reason codes for remaining sparse clustering states. Keep `message` human-readable. | DTO/schema and API response tests. | 1D |
| Public objective component names | Global LP/diagnostics use `cluster_cost`; public objective naming must stay canonical. | Public objective components use canonical names: `raw_cost`, `production_cost`, `flow_cost`, `port_cost`, `cluster_cost`, `duplication_cost`, `unmet_demand_penalty`. | Do not introduce public aliases for canonical component names. | API, frontend rendering, and docs tests updated to canonical vocabulary. | 1C |
| Clustering defaults and guardrails ownership | Defaults/guardrails are duplicated across optimizer-core, API, frontend, and tests. Frontend currently sends some values that change backend default semantics. | Optimizer-core owns canonical defaults/guardrails. API exposes them through the existing `ProblemDto` returned by problem endpoints. Frontend consumes `ProblemDto` defaults when initializing editable problem state. | Avoid a broad config framework; use named optimizer-core constants/dataclasses and DTO mapping/tests. No new config endpoint for Phase 1B. | Optimizer-core default tests; API contract tests proving exposed values match optimizer-core; frontend initialization/request tests. | 1B |
| Sparse `max_refinement_passes` default | Backend `None` means mode-specific default (`fast` derives 1, `balanced` derives 8); frontend currently defaults to sending `8`. | Frontend should initialize this field empty/null unless the API-provided defaults explicitly set an override. Omitted/default values must preserve optimizer-core mode-specific semantics. | Fix this drift in Phase 1B; do not defer. | Frontend request serialization and API/optimizer default tests. | 1B |
| Numeric validation ranges/types | Some frontend validation is looser/different from API validation; invalid values can be coerced to `0`. | Frontend numeric settings use field-level validation and block invalid solve request serialization. Integer fields validate as integers, and ranges align with API/optimizer contracts. | No silent coercion of malformed non-empty numeric values. | Frontend validation/request serialization tests; API validation tests where affected. | 1B, 3 |
| Graph modes | Current graph behavior mixes raw flow display and frontend heuristic grouping without explicit mode separation. | Graph UI supports explicit modes: raw LP flow, heuristic grouping, and optimizer cluster overlay. | Heuristic grouping remains labeled as heuristic and must not be presented as optimizer clustering. | Frontend graph domain/UI tests. | 2B |
| Graph data source without explorer metadata | Current graph construction depends on explorer recipe metadata; current solve result does not carry enough recipe coefficients to reconstruct full topology alone. | Phase 2A uses the best available graph source without expanding the solve API: if explorer data is present, use it for topology even when stale/mismatched and show a separate warning; if explorer data is unavailable, render a partial ID-only solve graph from solve-result IDs and show a separate warning that recipe IO topology is unavailable. | Do not claim full raw topology can render from current `SolveResultDto` alone. Warnings must be separate from graph availability. No solve-result recipe IO metadata is added in Phase 2A. | Tests for unavailable/stale explorer behavior. | 2A |
| Optimizer cluster overlay completeness | Sparse recipe assignments can be capped. | Optimizer overlay is available only when the frontend can build a complete, unambiguous active recipe-to-cluster mapping. If sparse assignments are capped/missing, do not render a partial overlay; show an unavailable overlay warning instead. | Never silently render an incomplete cluster overlay as complete. Prefer clear unavailability over approximate cluster coloring. | Frontend overlay tests using capped/partial assignment cases. | 2B |
| Graph layout | Flow graph uses fixed constants and column layout. | Layout should adapt to graph size/mode where feasible. | Preserve user-visible design intent from any designer phase. | Frontend tests/build and UI review for substantial visual changes. | 2C |
| Graph detail recomputation | Selection details recompute cluster/graph information repeatedly. | Precompute graph/cluster detail indexes when building the view model. | Keep performance cleanup separate from mode/data-source semantics. | Frontend domain tests. | 2D |
| API/default-data config constants | Some path and limit values are duplicated or use fixed-depth parent traversal. | Use named config/helper functions for API limits, default-data resolution, and repo-local fallbacks. | Avoid creating a broad config framework unless required by real multi-environment needs. | API/default-data tests where practical. | 3 |

## Requirements

- **REQ-001**: Record accepted cleanup decisions in this document and keep `docs/code_hygiene_backlog.md` as the evidence register.
- **REQ-002**: Remove `exact-small` completely from optimizer mode definitions, API DTOs, frontend DTOs/UI, tests, and docs.
- **REQ-003**: Remove no-op sparse clustering fallback fields/helpers until a real fallback path exists.
- **REQ-004**: Optimizer-core owns canonical clustering defaults and guardrails; the API exposes them; the frontend consumes API-provided/defaulted values.
- **REQ-005**: Known sparse clustering failures use structured statuses with reason codes; unexpected exceptions fail the solve job visibly.
- **REQ-006**: Public objective component names use the canonical vocabulary: `raw_cost`, `production_cost`, `flow_cost`, `port_cost`, `cluster_cost`, `duplication_cost`, `unmet_demand_penalty`.
- **REQ-007**: Graph visualization supports explicit raw LP flow, heuristic grouping, and optimizer cluster overlay modes.
- **REQ-008**: Graph rendering degrades gracefully when explorer enrichment/package metadata is unavailable or stale, according to the Phase 2A data-source decision.
- **REQ-009**: Invalid numeric frontend settings show field-level validation errors and block invalid solve request serialization.
- **REQ-010**: Brittle path/config constants are centralized in named config/helpers.

## Constraints and guidelines

- **CON-001**: Frontend/API/optimizer boundaries from `AGENTS.md` remain in force.
- **CON-002**: Optimizer-core may not depend on API/frontend code.
- **CON-003**: Frontend communicates with backend only through HTTP/API DTOs.
- **GUD-001**: Prefer deleting obsolete compatibility scaffolding over keeping unsupported modes.
- **GUD-002**: Prefer named constants/dataclasses/helpers over broad configuration frameworks.
- **GUD-003**: Prefer explicit degraded states over silent fallbacks or generic failure messages.
- **GUD-004**: Keep visualization modes understandable; raw solve data, heuristic grouping, and optimizer clustering must not be silently conflated.

## Phase plan

### Phase 1A: Sparse mode/result schema cleanup

- Remove `exact-small` from optimizer-core, API DTOs, frontend DTOs/UI, tests, and docs.
- Remove no-op sparse clustering fallback fields/helpers.
- Update sparse clustering result DTOs and tests.

### Phase 1B: Defaults/guardrails contract

- Centralize sparse clustering defaults and guardrails in optimizer-core.
- Expose effective defaults/guardrails through the existing `ProblemDto` returned by problem endpoints; do not add a new config endpoint in Phase 1B.
- Fix frontend/backend default drift and numeric type/range mismatches that affect clustering requests.

### Phase 1C: Objective component vocabulary

- Keep public objective components on the canonical names.
- Remove frontend alias warnings made obsolete by the migration.

### Phase 1D: Failure reporting taxonomy

- Add minimal structured failure shape for known clustering failures: `status`, `reason_code`, `message`, optional `details`.
- Require `reason_code` for every non-success sparse clustering result and omit it for successful results.
- Use deterministic reason codes for remaining sparse clustering states.
- Let unexpected clustering exceptions fail the solve job rather than returning generic clustering failure payloads.

### Phase 2A: Graph data-source contract

- Implement best-available graph behavior when explorer metadata is unavailable/stale: use stale/mismatched explorer for topology with warnings when present; otherwise render a partial ID-only solve graph from solve-result IDs with a topology-unavailable warning.
- Document that current solve results cannot reconstruct full recipe topology without recipe IO metadata.

### Phase 2B: Explicit graph modes and overlay semantics

- Add explicit raw LP flow, heuristic grouping, and sparse cluster overlay modes.
- Make raw LP flow the ungrouped graph view.
- Keep current connected-component grouping only in the explicit heuristic grouping mode.
- Make sparse overlay available only for complete, unambiguous active recipe-to-cluster mappings; show an unavailable/ambiguous warning instead of rendering partial overlays for capped or missing sparse assignments.

### Phase 2C: Adaptive layout/rendering

- Replace fixed graph dimensions/columns with adaptive rendering where feasible.

### Phase 2D: Precomputed details/indexes and panel clarity

- Precompute graph/cluster detail indexes.
- Clarify deterministic diagnostics vs sparse post-process panels.

### Phase 3: General config/input polish

- Centralize remaining API/default-data config constants.
- Add remaining field-level numeric validation and request blocking.
- Add messages/docstrings for sentinel exceptions where useful.

## Validation checklist

- `exact-small` references are removed from optimizer/API/frontend/docs/tests where applicable.
- Sparse clustering result payloads no longer expose no-op fallback fields.
- Optimizer-core owns clustering defaults and frontend/API do not duplicate independent values.
- Known clustering failures use structured statuses/reason codes; unexpected exceptions fail visibly.
- Objective component names are normalized and old alias compatibility warnings are removed or unnecessary.
- Graph rendering does not silently conflate optimizer clusters with heuristic grouping.
- Graph behavior without explorer metadata follows the Phase 2A decision.
- Invalid frontend numeric settings cannot be serialized into solve requests.
- Path/config constants are centralized in named helpers/config.

## Related documents

- `docs/code_hygiene_backlog.md`
- `docs/sparse_graph_clustering.md`
- `docs/mathematical_model.md`
- `docs/data_interface.md`
- `AGENTS.md`
