# Importer workflow

The `game-data-extractor` commands prepare recipe data for later optimizer work. They do not
run a solver, build a GUI, or generate blueprints.

## Dump data.raw

The `dump-data` wrapper no longer extracts startup settings from a save archive
implicitly. Provide a separate startup settings JSON file when one is needed.
The wrapper validates that this file is readable JSON, stages a copy next to the
dump output, and records the underlying Factorio `--dump-data` command.

Only `--dry-run` is currently available. Non-dry-run exits with a structured
`factorio_dump_unavailable` error until a real isolated Factorio settings
workflow exists.

Dry-run the Factorio dump command shape:

```bash
uv run game-data-extractor dump-data \
  --factorio-bin /path/to/factorio \
  --settings /path/to/startup-settings.json \
  --mod-directory /path/to/mods \
  --output-dir data/generated/importer-workflow/dump \
  --dry-run
```

Non-dry-run is intentionally blocked for now:

```bash
uv run game-data-extractor dump-data \
  --factorio-bin /path/to/factorio \
  --settings /path/to/startup-settings.json \
  --mod-directory /path/to/mods \
  --output-dir data/generated/importer-workflow/dump
```

## Extract save settings

Use `extract-save-settings` when you have a supported save-settings fixture and
want to produce the startup settings JSON consumed by `dump-data`:

```bash
uv run game-data-extractor extract-save-settings \
  --save /path/to/save.zip \
  --output data/generated/importer-workflow/startup-settings.json
```

This command is separate from `dump-data`; `dump-data` only consumes an existing
settings JSON file.

## Normalize dump

```bash
uv run game-data-extractor normalize-dump \
  --dump data/generated/importer-workflow/dump/script-output/data-raw-dump.json \
  --output data/generated/importer-workflow/dataset.json \
  --diagnostics data/generated/importer-workflow/diagnostics.json
```

Normalized recipe coefficients use `a_ir`: positive values are outputs and
negative values are inputs.

## Export a milestone recipe set

```bash
uv run game-data-extractor export-milestone \
  --dataset data/generated/importer-workflow/dataset.json \
  --milestones examples/milestones.json \
  --milestone basic-circuits \
  --output data/generated/importer-workflow/basic-circuits.json
```

The export is an `OptimizerRecipeDataset` JSON containing only recipes available
at the milestone, the selected milestone result in `milestones`, and combined
dataset/milestone diagnostics.

## Export canonical factory data

Use `export-factory-data` to convert an `OptimizerRecipeDataset` into the
canonical optimizer/API `*.factory-data.json` package shape:

```bash
uv run game-data-extractor export-factory-data \
  --dataset data/generated/importer-workflow/dataset.json \
  --demand iron-plate=60/min \
  --accepted-input iron-ore \
  --output data/packages/default.factory-data.json
```

Demand rates use the same `ITEM=RATE/min` syntax as `plan` and are stored as
per-second rates in the package. If no `--accepted-input` flags are supplied, the
exporter uses the planner's default accepted-input policy.

## Report artifacts

```bash
uv run game-data-extractor report \
  --settings /path/to/startup-settings.json \
  --dataset data/generated/importer-workflow/dataset.json \
  --milestone-output data/generated/importer-workflow/basic-circuits.json
```

The report summarizes settings metadata when present, dump provenance,
normalized counts, diagnostics, and milestone recipe deltas/counts.

## Artifact policy

Write generated importer artifacts under `data/generated/`, not under `.omo/`.
The `.omo/` directory is reserved for agent/workflow scratch state. Do not commit
real saves, mod zip files, full `data.raw` dumps, or generated large datasets.
Keep only small hand-written fixtures and concise evidence files that are safe to
review. Small curated canonical packages may live under `data/packages/`; the API
prefers `data/packages/default.factory-data.json` after the explicit
`FACTORY_PLAN_DEFAULT_DATA_PATH` override.

The real-save smoke-test artifacts from local verification are stored in:

```text
data/generated/real-save-test/
```

Those artifacts include the copied `data.raw` dump, normalized dataset,
diagnostics, generated science milestones, and milestone recipe exports. The
directory is ignored by git through the `data/generated/` rule.

## Limitations

The current workflow is an importer only. A real Pyanodon import requires a
user-provided save, matching mods, and a Factorio executable. The repository does
not claim full Pyanodon import coverage without those external artifacts.
