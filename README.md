# skyblock-data

Versioned mirror of the SkyBlock entity data consumed by [SkyBlock-Simplified](https://github.com/skyblock-simplified/SkyBlock-Simplified). This repository is the upstream source of truth for items, mobs, progression systems, stat modifiers, and world content. All files are plain JSON keyed by natural id.

## Structure

```
data/
└── v1/
    ├── index.json               # manifest (generated)
    ├── items/                   # 6 files - in-game items and item registry
    ├── mobs/                    # 4 files - monster taxonomy and bestiary
    ├── player/                  # 6 files - player progression systems
    ├── modifiers/               # 19 files - stats, enchantments, reforges, bonuses
    └── world/                   # 7 files - regions, zones, NPCs, world events
```

The `v1/` directory is versioned so future breaking-schema changes can ship under `v2/` without disrupting existing consumers.

## index.json

`data/v1/index.json` is a machine-readable manifest that consumers use to discover files without hard-coding paths. It is regenerated automatically by `scripts/generate_index.py` and must be kept in sync with the on-disk contents - CI fails any pull request whose index is stale.

Schema:

```json
{
  "version": 1,
  "generated_at": "2026-04-08T12:34:56Z",
  "commit_sha": "abc123...",
  "count": 41,
  "files": [
    {
      "path": "data/v1/world/regions.json",
      "category": "world",
      "table_name": "regions",
      "model_class": "dev.sbs.minecraftapi.persistence.model.Region",
      "content_sha256": "a1b2c3...",
      "bytes": 3166,
      "has_extra": false
    },
    {
      "path": "data/v1/items/items.json",
      "category": "items",
      "table_name": "items",
      "model_class": "dev.sbs.minecraftapi.persistence.model.Item",
      "content_sha256": "f9e8d7...",
      "bytes": 7242564,
      "has_extra": true,
      "extra_path": "data/v1/items/items_extra.json",
      "extra_sha256": "deadbeef...",
      "extra_bytes": 259
    }
  ]
}
```

- `count` is the number of distinct entities (41), not the raw file count. `has_extra: true` flags entities that have an `_extra` companion file, which is merged into the primary file at load time.
- `content_sha256` is a lowercase hex digest of the file bytes as stored on disk. Consumers use it for change detection.
- `table_name` matches the `@Table(name = "...")` JPA annotation on the corresponding Java model.
- `model_class` is the fully-qualified class name in the SkyBlock-Simplified `minecraft-api` module.
- `path` is always relative to the repo root and is exactly what a Feign `getFile(path)` call should request.

## Consumer workflow

Consumers fetch `data/v1/index.json` once, then fetch individual files by `path`. Change detection is SHA-256 based: re-fetch `index.json` periodically, diff `content_sha256` values, and re-download only the files that changed. This is the pattern `simplified-data` uses in its asset polling pipeline.

The initial reference consumer is the `simplified-data` Spring Boot module in SkyBlock-Simplified. See its `CLAUDE.md` for integration details.

## Contributing

1. Fork and clone
2. Edit or add JSON files under `data/v1/<category>/`
3. Run `python scripts/generate_index.py` to regenerate `data/v1/index.json`
4. Stage both the JSON edits AND the updated `index.json`, commit, open a PR
5. CI will verify the index is in sync; if it is not, the PR check fails and you must rerun the generator locally

The generator requires Python 3.8 or newer with the standard library only (no external dependencies).

### Adding a new file

New files require a matching entry in the `MODEL_CLASS_BY_TABLE` dict at the top of `scripts/generate_index.py`. Without that entry the generator refuses to emit the index, because the `model_class` field cannot be inferred from the filename alone (English plural irregularities). Add your new table there at the same time you add the JSON file.

## License

Apache License 2.0 - see [LICENSE.md](LICENSE.md).

Data content is derived from public Hypixel API responses and community knowledge. Individual entry-level copyrights, where they exist, belong to their respective owners. The repository as a compilation is licensed under Apache 2.0.
