# Data directory

`data/raw/default-data-raw-dump.json` is the single source of truth for the
default real game data. It is an extracted `data.raw` dump and includes the
technology prerequisite graph and technology science-pack ingredients.

`data/generated/` contains reproducible artifacts derived from that raw dump:

- `default-game-data.json` — normalized extractor dataset.
- `technology-prerequisite-graph.json` — concise technology graph helper.
- `milestone-recipe-sets.json` — nested science milestone recipe reachability.
- `default.factory-data.json` — canonical optimizer/API package.
- `normalization-diagnostics.json` — diagnostics from normalization.

The API uses `FACTORY_PLAN_DEFAULT_DATA_PATH` when set. Otherwise, it loads
`data/generated/default.factory-data.json`, then falls back to the toy example
under `examples/data/`.

Regenerate all default artifacts from the raw source with:

```bash
cd backend/game-data-extractor
uv run python -m game_data_extractor normalize-dump \
  --dump ../../data/raw/default-data-raw-dump.json \
  --output ../../data/generated/default-game-data.json \
  --diagnostics ../../data/generated/normalization-diagnostics.json
uv run python -m game_data_extractor export-technology-graph \
  --dataset ../../data/generated/default-game-data.json \
  --output ../../data/generated/technology-prerequisite-graph.json
uv run python -m game_data_extractor export-factory-data \
  --dataset ../../data/generated/default-game-data.json \
  --demand automation-science-pack=60/min \
  --demand py-science-pack-1=60/min \
  --demand logistic-science-pack=60/min \
  --output ../../data/generated/default.factory-data.json
```

`default.factory-data.json` embeds milestone recipe sets. Refresh the standalone
helper copy with:

```bash
cd backend/game-data-extractor
uv run python -c 'import json; from pathlib import Path; from game_data_extractor.data_contracts import FactoryDataPackage; package=FactoryDataPackage.from_json(Path("../../data/generated/default.factory-data.json").read_text()); Path("../../data/generated/milestone-recipe-sets.json").write_text(json.dumps({"milestones":[m.to_json_value() for m in package.milestones]}, indent=2, sort_keys=True)+"\\n")'
```
