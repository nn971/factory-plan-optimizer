---
sessionID: ses_0c2dfb9a7ffevugiusbqiIsivi
baseMessageCount: 0
updatedAt: 2026-07-07T15:30:30.300Z
version: 1.0
date_created: 2026-07-07
owner: agent
tags: [spec, diagnostic]
---

# Move the data extraction codes to a folder parallel to optimizer-core and api.

## Current spec

# Introduction
This specification defines a one-time atomic refactor for moving data extraction/import-related code out of `backend/optimizer-core` into a new full `uv` workspace package at `backend/game-data-extractor`. The goal is to clarify package boundaries, remove extraction workflow concerns from optimizer-core internals, expose shared data contracts through `game_data_extractor.data_contracts`, and make extraction workflows independently maintainable while preserving optimizer and API behavior.

## 1. Purpose & Scope
Intended audience: maintainers of the factory plan optimizer repository.

Scope:
- Create `backend/game-data-extractor` as a full `uv` workspace package parallel to `backend/optimizer-core` and `backend/api`.
- Move current extraction/import modules from `backend/optimizer-core/src/factory_plan_optimizer/` into the new `game-data-extractor` package.
- Expose `FactoryDataPackage` types plus importer dataset models from `game_data_extractor.data_contracts`.
- Allow JSON serialization helpers such as `from_json` and `to_json` in `game_data_extractor.data_contracts` where they are part of contract-level model behavior.
- Allow optimizer-core and API to depend on `game_data_extractor.data_contracts` only, not on extraction workflow modules.
- Move all discovered extraction/import/report/validate CLI subcommands to the new `game-data-extractor` executable only.
- Implement the migration as one atomic refactor that lands without compatibility shims.
- Update imports, tests, package/workspace configuration, CLI wiring, `docs/importer_workflow.md`, `docs/data_interface.md`, and `AGENTS.md` guidance affected by the move.

Current extraction/import code identified in scope:
- `import_models.py`
- `import_dataset_models.py`
- `import_recipe_models.py`
- `import_provenance_models.py`
- `import_provenance_parsing.py`
- `import_parsing.py`
- `data_raw_normalization.py`
- `milestones.py`
- `save_settings.py`
- `dump_data.py`
- `dump_data_cli.py`
- extraction/import command dispatch currently wired through `factory_plan_optimizer.__main__`

Current CLI subcommands to move to `game-data-extractor`:
- `extract-save-settings`
- `dump-data`
- `normalize-dump`
- `export-milestone`
- `export-factory-data`
- `report`
- `validate-dataset`

Out of scope:
- Changing optimization behavior.
- Changing frontend behavior.
- Adding new extraction features.
- Adding blueprint generation, neural nets, train scheduling, spoilage handling, or GUI-heavy behavior.
- Making non-dry-run `dump-data` actually execute Factorio; current dry-run-only behavior should remain unless separately specified.
- Staged PR migration or temporary compatibility shims.

## 2. Definitions
- Data extraction: Code that reads, derives, or dumps source data from Factorio-related sources and prepares it for repository use.
- Importer: Code that transforms extracted/generated data into repository data structures or optimizer-facing data contracts.
- Optimizer core: The package in `backend/optimizer-core`, currently named `factory-plan-optimizer`, containing optimization models, planning adapters, and solver logic.
- API: The HTTP service package in `backend/api`.
- `game-data-extractor`: The new full `uv` workspace package at `backend/game-data-extractor` and executable CLI command for extraction/import workflows.
- `game_data_extractor.data_contracts`: The public module inside `game-data-extractor` that contains `FactoryDataPackage` types plus importer dataset models shared with optimizer-core and, if needed, API. It may include contract-level JSON helpers such as `from_json` and `to_json`.
- Workflow module: Any `game-data-extractor` module that performs extraction, parsing orchestration, normalization, provenance handling, CLI behavior, reporting, validation orchestration, or file/process orchestration.
- Atomic refactor: A single landing change that updates package structure, imports, CLI ownership, tests, and docs together, without temporary compatibility layers.
- Compatibility shim: A temporary module, CLI alias, or import path that forwards old callers to the new location. This refactor must not keep such shims by default.
- `FactoryDataPackage`: The canonical optimizer-facing data contract documented in `docs/data_interface.md`.

## 3. Requirements, Constraints & Guidelines
- **REQ-001**: Create `backend/game-data-extractor` as a full `uv` workspace package parallel to `backend/optimizer-core` and `backend/api`.
- **REQ-002**: Add `backend/game-data-extractor` to the root `uv` workspace members.
- **REQ-003**: Move extraction/import-related code into `game-data-extractor`.
- **REQ-004**: Expose `FactoryDataPackage` types plus importer dataset models from `game_data_extractor.data_contracts`.
- **REQ-005**: Allow contract-level JSON helpers such as `from_json` and `to_json` in `game_data_extractor.data_contracts`.
- **REQ-006**: Allow optimizer-core to import only `game_data_extractor.data_contracts` from `game-data-extractor`.
- **REQ-007**: Allow API to import only `game_data_extractor.data_contracts` from `game-data-extractor` if needed.
- **REQ-008**: Prevent optimizer-core and API from importing `game-data-extractor` workflow modules.
- **REQ-009**: Move `extract-save-settings`, `dump-data`, `normalize-dump`, `export-milestone`, `export-factory-data`, `report`, and `validate-dataset` to the new `game-data-extractor` executable only.
- **REQ-010**: Remove moved extraction/import/report/validate commands from the optimizer-core CLI dispatch rather than forwarding through compatibility shims.
- **REQ-011**: Update all known callers to use the new import paths and command locations.
- **REQ-012**: Do not preserve old import paths or CLI entry points as temporary compatibility shims.
- **REQ-013**: Preserve existing public behavior for moved commands unless an intentional behavior change is explicitly documented.
- **REQ-014**: Update tests, package/workspace metadata, and documentation affected by the move.
- **REQ-015**: Preserve current `dump-data` behavior: `--dry-run` is supported and non-dry-run returns the structured `factorio_dump_unavailable` result/error as currently documented and tested.
- **REQ-016**: Ensure command examples in `docs/importer_workflow.md` are updated to the new `game-data-extractor` CLI structure.
- **REQ-017**: Update `AGENTS.md` to include `backend/game-data-extractor` checks and revised workspace/boundary guidance.
- **REQ-018**: Land the migration as one atomic refactor rather than a staged PR plan.
- **SEC-001**: Do not commit real saves, mod zips, full `data.raw` dumps, secrets, or generated large datasets.
- **CON-001**: The root `uv` workspace currently lists only `backend/api` and `backend/optimizer-core`; this refactor must update root `pyproject.toml` to include `backend/game-data-extractor`.
- **CON-002**: Optimizer internals under `backend/optimizer-core/src/factory_plan_optimizer/optimizer/` must not import extraction/import workflow modules.
- **CON-003**: The canonical optimizer-facing data contract remains `FactoryDataPackage` as documented in `docs/data_interface.md`.
- **CON-004**: API boundaries must continue to prevent API imports of CLI/extraction workflow internals.
- **CON-005**: Since shared contracts live inside `game-data-extractor`, package boundaries must distinguish `game_data_extractor.data_contracts` from private workflow modules.
- **GUD-001**: Keep `game-data-extractor` focused on data acquisition, normalization, provenance, importer dataset parsing, export workflows, reporting/validation commands, and public data contracts.
- **GUD-002**: Prefer explicit import updates over compatibility layers so stale boundaries fail clearly.
- **GUD-003**: Keep examples and generated artifacts small and reviewable.
- **GUD-004**: Keep `game_data_extractor.data_contracts` minimal and stable; avoid forcing optimizer-core or API to depend on extractor workflow logic.
- **GUD-005**: Keep JSON helpers in `data_contracts` limited to serialization/deserialization of contract models; workflow-specific parsing should remain outside the public contract module.

## 4. Interfaces & Data Contracts
Current verified contracts and interfaces:
- `FactoryDataPackage` is the canonical optimizer-facing contract documented in `docs/data_interface.md`.
- `OptimizerRecipeDataset` is the current importer dataset model in `import_dataset_models.py`, with `from_json` and `to_json` helpers.
- Importer prototype/provenance models currently include item, recipe, technology, resource source, save settings provenance, dump provenance, milestone, and diagnostic structures across the `import_*` modules.
- `planning.py` currently adapts importer datasets into `FactoryDataPackage` for optimizer consumption.

Target contract direction:
- `FactoryDataPackage` types and importer dataset models should live in `game_data_extractor.data_contracts`.
- Contract-level JSON helpers such as `from_json` and `to_json` may live in `game_data_extractor.data_contracts`.
- Optimizer-core may import public contract types from `game_data_extractor.data_contracts`.
- API may import public contract types from `game_data_extractor.data_contracts` if needed.
- Optimizer-core and API must not import `game-data-extractor` workflow modules for parsing orchestration, dumping, normalization, save settings extraction, CLI behavior, reporting, validation orchestration, or provenance orchestration.
- Extraction workflow modules should produce public contract objects or serialized JSON compatible with the documented `FactoryDataPackage` contract.

Target CLI direction:
- The executable command is `game-data-extractor`.
- The moved subcommands are `extract-save-settings`, `dump-data`, `normalize-dump`, `export-milestone`, `export-factory-data`, `report`, and `validate-dataset`.
- The optimizer-core CLI should retain optimizer-owned commands only.
- Old optimizer-core extraction/import/report/validate command entry points should be removed rather than shimmed.

## 5. Acceptance Criteria
- **AC-001**: Given the refactor branch, When optimizer-core checks are run, Then optimizer tests pass without optimizer internals importing extraction/import workflow modules.
- **AC-002**: Given the refactor branch, When API checks are run, Then API behavior remains compatible with existing endpoints and API boundary tests continue to prevent API imports of CLI/extraction workflow internals.
- **AC-003**: Given `backend/game-data-extractor`, When extraction/import tests are run, Then moved code behaves the same as before the move.
- **AC-004**: Given old extraction/import import paths in repository-owned code, When the refactor is complete, Then they have been updated to the new paths rather than routed through shims.
- **AC-005**: Given repository documentation, When a maintainer looks for extraction/import ownership, Then `backend/game-data-extractor`, its commands, and boundaries are documented.
- **AC-006**: Given `dump-data --dry-run`, When the command is run through `game-data-extractor` after the refactor, Then it produces the same dry-run/provenance behavior currently covered by tests.
- **AC-007**: Given non-dry-run `dump-data`, When the command is run through `game-data-extractor` after the refactor, Then it still returns the structured `factorio_dump_unavailable` behavior unless a separate spec changes that behavior.
- **AC-008**: Given the optimizer-core CLI, When a user invokes moved extraction/import/report/validate subcommands, Then those commands are no longer available from optimizer-core.
- **AC-009**: Given optimizer-core code that needs shared data types, When imports are inspected, Then it imports only `game_data_extractor.data_contracts` and not workflow modules.
- **AC-010**: Given API code that needs shared data types, When imports are inspected, Then it imports only `game_data_extractor.data_contracts` and not workflow modules.
- **AC-011**: Given the root workspace, When `uv lock --dry-run` is run after the refactor, Then the workspace resolves with `backend/game-data-extractor` included.
- **AC-012**: Given the completed branch, When old CLI and import paths are searched, Then no repository-owned source or tests rely on removed shim paths.
- **AC-013**: Given `AGENTS.md`, When maintainers read command guidance, Then it includes `backend/game-data-extractor` checks and updated boundary rules.
- **AC-014**: Given `game_data_extractor.data_contracts`, When imports are inspected, Then contract-level JSON helpers do not import private workflow modules.

## 6. Test Automation Strategy
Use the existing Python test stack and move/add tests with the affected packages.

Required test updates:
- Move or update tests covering `dump_data`, importer parsing, normalization, milestones, save settings, reporting, validation, and CLI dispatch into the `backend/game-data-extractor` test area.
- Keep or adapt `backend/optimizer-core/tests/test_optimizer_boundary.py` so optimizer internals cannot import extraction/import workflow modules.
- Keep or adapt `backend/api/tests/test_boundaries.py` so API code cannot import CLI/extraction workflow internals.
- Add boundary coverage distinguishing `game_data_extractor.data_contracts` from `game-data-extractor` workflow modules.
- Add search/import checks proving old `factory_plan_optimizer.import_*` call sites have been migrated.
- Add CLI tests proving all moved subcommands are exposed by `game-data-extractor` and not by the optimizer-core CLI.
- Add contract tests for JSON helpers that remain in `game_data_extractor.data_contracts`.

Validation commands should include, at minimum:
- optimizer-core pytest/ruff/format/mypy checks from `backend/optimizer-core`
- API pytest/ruff/format/mypy checks from `backend/api`
- `game-data-extractor` pytest/ruff/format/mypy checks from `backend/game-data-extractor`
- root `uv lock --dry-run`

## 7. Rationale & Context
Current extraction/import code lives inside `backend/optimizer-core`, even though repository rules already distinguish importer responsibilities from optimizer responsibilities. Moving this code to `backend/game-data-extractor` makes the architecture match the intended boundary: extraction/import code prepares data, while optimizer-core consumes canonical data contracts.

Making `game-data-extractor` a full `uv` workspace package gives the refactor real packaging and test boundaries instead of only a source-tree rearrangement.

Placing `FactoryDataPackage` types plus importer dataset models in `game_data_extractor.data_contracts` avoids creating an additional contract-only package, but it makes boundary enforcement more important. Optimizer-core and API may depend on `game-data-extractor` for public contract types only, so tests should prevent imports of extractor workflow modules.

Allowing contract-level JSON helpers preserves existing model ergonomics, such as `from_json` and `to_json`, without requiring optimizer-core to depend on private extraction workflow modules.

Moving all discovered extraction/import/report/validate commands to the `game-data-extractor` CLI reinforces ownership. The optimizer-core CLI should not be responsible for data extraction or importer workflow commands once those modules are moved.

Updating `AGENTS.md` is required because it currently documents workspace members, check commands, boundaries, and `dump-data` behavior. Those instructions must remain accurate after the package split.

The migration will land atomically without compatibility shims. This favors clean boundaries and avoids preserving stale module names, at the cost of requiring a complete import/command migration in one change.

## 8. Dependencies & External Integrations
- **EXT-001**: Root `uv` workspace configuration in `pyproject.toml`, currently with members `backend/api` and `backend/optimizer-core`; target state includes `backend/game-data-extractor`.
- **EXT-002**: Optimizer-core package configuration in `backend/optimizer-core/pyproject.toml`, currently exposing CLI entry point `factory-plan-optimizer = factory_plan_optimizer.__main__:main`.
- **EXT-003**: API package configuration in `backend/api/pyproject.toml`, currently depending on local workspace package `factory-plan-optimizer`.
- **EXT-004**: New `game-data-extractor` executable CLI entry point, exact module path pending implementation.
- **EXT-005**: Public data contract module `game_data_extractor.data_contracts`.
- **EXT-006**: Factorio-related extraction inputs used by `dump-data`, including `--factorio-bin`, `--settings`, `--mod-directory`, and `--output-dir`.
- **EXT-007**: Generated artifacts under `data/generated/`, which must not include committed real saves, mod zips, full raw dumps, or large generated datasets.
- **EXT-008**: Documentation in `docs/data_interface.md`, `docs/importer_workflow.md`, `docs/mathematical_model.md`, and `AGENTS.md`.

## 9. Examples & Edge Cases
Current command examples to preserve/update are documented in `docs/importer_workflow.md` and include workflows around:
- `dump-data`
- `normalize-dump`
- `export-milestone`
- `export-factory-data`
- `extract-save-settings`
- `report`
- `validate-dataset`

Target command examples should use the new `game-data-extractor` executable, for example `game-data-extractor dump-data ...` once implemented.

Edge cases to validate:
- Existing CLI dispatch in `factory_plan_optimizer.__main__` references moved modules.
- Tests import old `factory_plan_optimizer.import_*` paths.
- Generated data paths assume old package-relative locations.
- Optimizer code accidentally imports extraction/import workflow modules after the move.
- API code imports extraction/CLI internals after the move.
- `dump-data` accidentally attempts real external Factorio execution despite current dry-run-only design.
- Documentation snippets show old command names, package names, or import paths.
- `game_data_extractor.data_contracts` starts importing private workflow modules, creating accidental reverse coupling.
- JSON helper methods in `data_contracts` grow into workflow parsing/orchestration logic.
- Workspace configuration is updated without updating lock/check instructions.
- `AGENTS.md` remains stale and tells maintainers that workspace members are only `backend/api` and `backend/optimizer-core`.
- Atomic migration misses a repository-owned caller because no shim remains to catch it later.

## 10. Validation Criteria
Validation should include:
- Optimizer-core package checks from `backend/optimizer-core`.
- API package checks from `backend/api`.
- `game-data-extractor` package checks from `backend/game-data-extractor`.
- Root `uv lock --dry-run` after workspace/package metadata changes.
- Search-based verification that old import paths are removed from repository-owned source and tests.
- Boundary verification that optimizer internals do not import extraction/import workflow modules.
- Boundary verification that API code does not import CLI/extraction workflow internals.
- Boundary verification that optimizer-core imports only `game_data_extractor.data_contracts` from `game-data-extractor`.
- Boundary verification that API imports only `game_data_extractor.data_contracts` from `game-data-extractor` if it imports the package at all.
- Boundary verification that `game_data_extractor.data_contracts` does not import private workflow modules.
- CLI verification that all moved subcommands exist only on `game-data-extractor`.
- Contract verification that `from_json` and `to_json` helpers remain serialization helpers and do not perform workflow orchestration.
- Documentation verification that `docs/importer_workflow.md`, `docs/data_interface.md`, and `AGENTS.md` describe the new ownership, checks, boundaries, and command paths.

## 11. Related Specifications / Further Reading
- `docs/data_interface.md`: canonical `FactoryDataPackage` contract and importer-vs-optimizer responsibilities.
- `docs/importer_workflow.md`: current importer workflow and command examples.
- `docs/mathematical_model.md`: optimizer coefficient and objective conventions used downstream.
- `AGENTS.md`: repository boundary rules, workspace notes, command checks, and `dump-data` dry-run-only note.
- Root `pyproject.toml`: current `uv` workspace membership.
- `backend/optimizer-core/pyproject.toml`: current optimizer package and CLI entry point.
- `backend/api/pyproject.toml`: current API package dependency on optimizer-core.

## Q&A history

Q: Should the moved data extraction code become a full workspace package or just a sibling source folder?
A: Decide after discovery

Q: Should old import paths/CLI entry points be kept temporarily as compatibility shims?
A: Break and update all callers

Q: What dependency boundary should the new extraction package/folder follow?
A: Create/shared data contract package or module

Q: Where should extraction/import CLI commands live after the move?
A: New extraction CLI only

Q: What names should the new extraction package and CLI use?
A: game-data-extractor

Q: Where should the shared data contracts live?
A: Inside extraction package public module

Q: Should `game-data-extractor` be a full `uv` workspace package?
A: Yes, add workspace member

Q: What should the public contract module inside `game-data-extractor` be called?
A: game_data_extractor.data_contracts

Q: Where should the new workspace package directory live?
A: backend/game-data-extractor

Q: Which contracts should move into `game_data_extractor.data_contracts`?
A: FactoryDataPackage plus importer dataset models

Q: What should the executable CLI command be called?
A: game-data-extractor

Q: Should implementation be one atomic refactor or staged internally while still landing without shims?
A: One atomic refactor

Q: Which currently discovered CLI subcommands should move to `game-data-extractor`?
A: All listed extraction/import/report/validate commands

Q: Should the API be allowed to depend directly on `game_data_extractor.data_contracts` if needed?
A: Yes, public contracts only

Q: Should `game_data_extractor.data_contracts` include JSON helper methods like `from_json`/`to_json`?
A: Yes, serialization helpers allowed

Q: Should `AGENTS.md` command guidance be updated to include `backend/game-data-extractor` checks?
A: Yes, update AGENTS.md
