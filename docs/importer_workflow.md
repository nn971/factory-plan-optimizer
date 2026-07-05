# Importer workflow

The importer commands prepare recipe data for later optimizer work. They do not
run a solver, build a GUI, or generate blueprints.

## Save-derived settings

Extract startup settings from a user-provided save artifact:

```bash
python -m factory_plan_optimizer extract-save-settings \
  --save /path/to/save.zip \
  --factorio-bin /path/to/factorio \
  --mod-directory /path/to/mods \
  --output .omo/evidence/task-3-settings.json
```

## Dump data.raw

The `dump-data` wrapper prepares the selected save-derived settings and records
the underlying Factorio `--dump-data` command. Only `--dry-run` is currently
available. Non-dry-run exits with a structured `factorio_dump_unavailable` error
until a real isolated Factorio settings workflow exists.

Dry-run the Factorio dump command shape:

```bash
python -m factory_plan_optimizer dump-data \
  --factorio-bin /path/to/factorio \
  --settings .omo/evidence/task-3-settings.json \
  --mod-directory /path/to/mods \
  --output-dir .omo/evidence/dump \
  --dry-run
```

Non-dry-run is intentionally blocked for now:

```bash
python -m factory_plan_optimizer dump-data \
  --factorio-bin /path/to/factorio \
  --settings .omo/evidence/task-3-settings.json \
  --mod-directory /path/to/mods \
  --output-dir .omo/evidence/dump
```

## Normalize dump

```bash
python -m factory_plan_optimizer normalize-dump \
  --dump .omo/evidence/dump/script-output/data-raw-dump.json \
  --output .omo/evidence/task-5-dataset.json \
  --diagnostics .omo/evidence/task-5-diagnostics.json
```

Normalized recipe coefficients use `a_ir`: positive values are outputs and
negative values are inputs.

## Export a milestone recipe set

```bash
python -m factory_plan_optimizer export-milestone \
  --dataset .omo/evidence/task-5-dataset.json \
  --milestones examples/milestones.json \
  --milestone basic-circuits \
  --output .omo/evidence/task-6-basic-circuits.json
```

The export is an `OptimizerRecipeDataset` JSON containing only recipes available
at the milestone, the selected milestone result in `milestones`, and combined
dataset/milestone diagnostics.

## Report artifacts

```bash
python -m factory_plan_optimizer report \
  --settings .omo/evidence/task-3-settings.json \
  --dataset .omo/evidence/task-5-dataset.json \
  --milestone-output .omo/evidence/task-6-basic-circuits.json
```

The report summarizes save settings provenance, dump provenance when present,
normalized counts, diagnostics, and milestone recipe deltas/counts.

## Artifact policy

Do not commit real saves, mod zip files, full `data.raw` dumps, or generated
large datasets. Keep only small hand-written fixtures and concise evidence files
that are safe to review.

## Limitations

The current workflow is an importer only. A real Pyanodon import requires a
user-provided save, matching mods, and a Factorio executable. The repository does
not claim full Pyanodon import coverage without those external artifacts.
