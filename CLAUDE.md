# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`skyblock-data` is a standalone data-only repository - **not** part of the SkyBlock-Simplified Java monorepo that sits above it on disk. It ships versioned JSON under `data/v1/` that the `simplified-data` module in SkyBlock-Simplified consumes over HTTP via a Feign client. The Java-flavored conventions in the parent `CLAUDE.md` (Lombok, Concurrent collections, Javadoc style, etc.) do not apply here.

## Commands

```bash
python scripts/generate_index.py            # regenerate data/v1/index.json
python scripts/generate_index.py --check    # verify index is in sync (CI mode)
```

Python 3.8+, standard library only - no virtualenv, no dependencies. Always run the generator after editing any file under `data/v1/` and commit the refreshed `index.json` in the same commit; otherwise the `Regenerate Index` workflow's PR check fails.

## Architecture

- **`data/v1/<category>/<table>.json`** is the on-disk layout. `<table>` is the JPA `@Table(name=...)` of the corresponding `dev.sbs.minecraftapi.persistence.model` class in the consumer repo. Categories (`items`, `mobs`, `modifiers`, `player`, `world`) are presentational only - consumers read `index.json`, not directory names.

- **`<table>_extra.json`** is an optional companion file merged into its primary at load time. Extras have no registered model class of their own; they need a matching primary or the generator aborts with an "orphan extra" error.

- **`data/v1/index.json`** is the sole entry point for consumers. They fetch it, diff `content_sha256` values against their cache, and refetch only changed files. Never hand-edit it - always regenerate.

- **`MODEL_CLASS_BY_TABLE` in `scripts/generate_index.py`** is the authoritative table-name -> Java FQN map. Adding a new JSON file requires adding a matching entry in the same commit; the generator refuses to emit an index for an unregistered table and likewise refuses if a registered table has no file (stale entry). English plural irregularities are why this is a dict instead of a derived mapping.

- **`v1/` is a schema-version boundary.** Breaking changes ship as `v2/` alongside - do not mutate `v1/` schema in place. `DATA_VERSION` in the generator locks it to the current major version.

## Determinism rules

The `content_sha256` in `index.json` must match bit-for-bit between Windows contributors and Linux CI:

- `.gitattributes` forces `eol=lf` on all text files. Do not disable `core.autocrlf` handling or commit CRLF-ending JSON.
- The generator writes `index.json` via `write_bytes` (not `write_text`) so Windows does not translate `\n` to `\r\n`.
- JSON output uses `indent=2, sort_keys=True` with a trailing newline. Preserve this formatting if you ever edit the generator's serializer.
- `generated_at` and `commit_sha` are excluded from `--check` comparison so regenerations without real content changes are no-ops.

## CI behavior

`.github/workflows/regenerate-index.yml` has two modes:
- **PRs**: run `--check`, fail if the committed index is stale. The contributor must regenerate locally and push.
- **Pushes to master**: run write mode and auto-commit any refreshed `index.json` as `github-actions[bot]`. This catches squash-merges that lost the regenerated index.

Only files under `data/v1/**`, `scripts/generate_index.py`, and the workflow itself trigger the job.
