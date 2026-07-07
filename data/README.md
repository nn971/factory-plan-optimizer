# Data directory

`data/packages/` contains small curated canonical `*.factory-data.json` packages
that are safe to review and commit. The API uses
`data/packages/default.factory-data.json` as its preferred default package after
`FACTORY_PLAN_DEFAULT_DATA_PATH`; if it is absent, the API falls back to the toy
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
