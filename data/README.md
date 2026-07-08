# Data directory

`data/packages/` contains small curated canonical `*.factory-data.json` packages
that are safe to review and commit. The API uses `FACTORY_PLAN_DEFAULT_DATA_PATH`
when set. Otherwise, it prefers the ignored generated real-data default at
`data/generated/real-plan-test/logistic-science.factory-data.json` when present,
then falls back to `data/packages/default.factory-data.json`, then to the toy
example under `examples/data/`.

Generated importer artifacts belong under `data/generated/` and should not be
committed when they are large, machine-local, or derived from real saves/mods.
Do not commit real saves, mod zips, full `data.raw` dumps, or large generated
datasets.

To create a curated package from an extractor dataset:

```bash
uv run game-data-extractor export-factory-data \
  --dataset data/generated/importer-workflow/dataset.json \
  --demand iron-plate=60/min \
  --accepted-input iron-ore \
  --output data/packages/default.factory-data.json
```

If `--accepted-input` is omitted, the exporter uses the planner's default raw
input policy.

The exporter writes canonical `factory-data-v2` packages. For local real-data
explorer testing, regenerate the ignored default from an existing normalized
dataset with:

```bash
uv run --package game-data-extractor game-data-extractor export-factory-data \
  --dataset data/generated/real-save-test/dataset.json \
  --demand automation-science-pack=3/min \
  --demand logistic-science-pack=1/min \
  --demand py-science-pack-1=2/min \
  --output data/generated/real-plan-test/logistic-science.factory-data.json
```
