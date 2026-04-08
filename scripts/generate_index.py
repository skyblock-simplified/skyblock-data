#!/usr/bin/env python3
"""Generate or verify data/v1/index.json for the skyblock-data repository.

The index is a machine-readable manifest that consumers use to discover files
without hard-coding paths. It is regenerated from the on-disk contents of
data/v1/ and committed alongside the files it describes. CI runs this script
in --check mode on every pull request and fails if the committed index is out
of sync with the tree.

Usage:
    python scripts/generate_index.py               # write data/v1/index.json
    python scripts/generate_index.py --check       # verify, exit 1 if stale
    python scripts/generate_index.py --help

Requirements: Python 3.8 or newer, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Authoritative mapping: table name -> fully-qualified Java class name.
#
# The table name is the stem of the primary JSON file (e.g., "items" for
# "items.json"). The model class is the @Table-annotated JpaModel subclass in
# minecraft-api. When a new JSON file is added under data/v1/, add its table
# here in the same commit - the generator refuses to emit an index for any
# file whose table is not registered.
# ---------------------------------------------------------------------------

MODEL_PACKAGE = "dev.sbs.minecraftapi.persistence.model"

MODEL_CLASS_BY_TABLE: Dict[str, str] = {
    "accessories": f"{MODEL_PACKAGE}.Accessory",
    "bestiary_categories": f"{MODEL_PACKAGE}.BestiaryCategory",
    "bestiary_families": f"{MODEL_PACKAGE}.BestiaryFamily",
    "bestiary_subcategories": f"{MODEL_PACKAGE}.BestiarySubcategory",
    "bits_items": f"{MODEL_PACKAGE}.BitsItem",
    "bonus_armor_sets": f"{MODEL_PACKAGE}.BonusArmorSet",
    "bonus_enchantment_stats": f"{MODEL_PACKAGE}.BonusEnchantmentStat",
    "bonus_item_rarities": f"{MODEL_PACKAGE}.BonusItemRarity",
    "bonus_item_stats": f"{MODEL_PACKAGE}.BonusItemStat",
    "bonus_pet_ability_stats": f"{MODEL_PACKAGE}.BonusPetAbilityStat",
    "bonus_reforge_stats": f"{MODEL_PACKAGE}.BonusReforgeStat",
    "brews": f"{MODEL_PACKAGE}.Brew",
    "collections": f"{MODEL_PACKAGE}.Collection",
    "enchantments": f"{MODEL_PACKAGE}.Enchantment",
    "essences": f"{MODEL_PACKAGE}.Essence",
    "fairy_souls": f"{MODEL_PACKAGE}.FairySoul",
    "gemstones": f"{MODEL_PACKAGE}.Gemstone",
    "hot_potato_stats": f"{MODEL_PACKAGE}.HotPotatoStat",
    "hotm_perks": f"{MODEL_PACKAGE}.HotmPerk",
    "item_categories": f"{MODEL_PACKAGE}.ItemCategory",
    "items": f"{MODEL_PACKAGE}.Item",
    "keywords": f"{MODEL_PACKAGE}.Keyword",
    "mayors": f"{MODEL_PACKAGE}.Mayor",
    "melody_songs": f"{MODEL_PACKAGE}.MelodySong",
    "minions": f"{MODEL_PACKAGE}.Minion",
    "mixins": f"{MODEL_PACKAGE}.Mixin",
    "mob_types": f"{MODEL_PACKAGE}.MobType",
    "pet_items": f"{MODEL_PACKAGE}.PetItem",
    "pets": f"{MODEL_PACKAGE}.Pet",
    "potion_groups": f"{MODEL_PACKAGE}.PotionGroup",
    "potions": f"{MODEL_PACKAGE}.Potion",
    "powers": f"{MODEL_PACKAGE}.Power",
    "reforges": f"{MODEL_PACKAGE}.Reforge",
    "regions": f"{MODEL_PACKAGE}.Region",
    "shop_perks": f"{MODEL_PACKAGE}.ShopPerk",
    "skills": f"{MODEL_PACKAGE}.Skill",
    "slayers": f"{MODEL_PACKAGE}.Slayer",
    "stat_categories": f"{MODEL_PACKAGE}.StatCategory",
    "stats": f"{MODEL_PACKAGE}.Stat",
    "zodiac_events": f"{MODEL_PACKAGE}.ZodiacEvent",
    "zones": f"{MODEL_PACKAGE}.Zone",
}

DATA_VERSION = 1
INDEX_VERSION = 1
EXTRA_SUFFIX = "_extra"
INDEX_FILENAME = "index.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_hex(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit_sha(repo_root: Path) -> Optional[str]:
    """Return the current HEAD commit SHA, or None if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha if sha else None


def relative_forward(path: Path, repo_root: Path) -> str:
    """Return a repo-root-relative path with forward slashes."""
    return path.relative_to(repo_root).as_posix()


def classify_file(stem: str) -> Tuple[str, bool]:
    """Return (table_name, is_extra) for a JSON filename stem."""
    if stem.endswith(EXTRA_SUFFIX):
        return stem[: -len(EXTRA_SUFFIX)], True
    return stem, False


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------


def build_index(repo_root: Path) -> dict:
    """Walk data/v1/ and build the index dict."""
    data_root = repo_root / "data" / f"v{DATA_VERSION}"
    if not data_root.is_dir():
        raise SystemExit(f"error: data root not found: {data_root}")

    # Group files by (category, table_name). Each group has one primary and
    # optionally one _extra companion.
    primaries: Dict[Tuple[str, str], Path] = {}
    extras: Dict[Tuple[str, str], Path] = {}

    for category_dir in sorted(data_root.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        for json_file in sorted(category_dir.glob("*.json")):
            stem = json_file.stem
            table_name, is_extra = classify_file(stem)
            key = (category, table_name)
            if is_extra:
                if key in extras:
                    raise SystemExit(
                        f"error: duplicate extra for {category}/{table_name}: "
                        f"{extras[key].name} and {json_file.name}"
                    )
                extras[key] = json_file
            else:
                if key in primaries:
                    raise SystemExit(
                        f"error: duplicate primary for {category}/{table_name}: "
                        f"{primaries[key].name} and {json_file.name}"
                    )
                primaries[key] = json_file

    # Validate: every extra has a matching primary.
    for (category, table_name), extra_path in extras.items():
        if (category, table_name) not in primaries:
            raise SystemExit(
                f"error: orphan extra {relative_forward(extra_path, repo_root)} "
                f"has no matching primary file"
            )

    # Validate: every primary has a registered model class.
    unknown_tables = sorted(
        table_name for (_, table_name) in primaries.keys()
        if table_name not in MODEL_CLASS_BY_TABLE
    )
    if unknown_tables:
        raise SystemExit(
            "error: the following tables have no entry in MODEL_CLASS_BY_TABLE: "
            + ", ".join(unknown_tables)
            + "\nadd them to scripts/generate_index.py in the same commit"
        )

    # Validate: every registered model class has a matching primary file.
    found_tables = {table_name for (_, table_name) in primaries.keys()}
    stale_tables = sorted(set(MODEL_CLASS_BY_TABLE.keys()) - found_tables)
    if stale_tables:
        raise SystemExit(
            "error: MODEL_CLASS_BY_TABLE has entries with no matching primary file: "
            + ", ".join(stale_tables)
            + "\nremove them from scripts/generate_index.py if intentional"
        )

    # Build file entries, sorted by path for deterministic output.
    files: List[dict] = []
    for (category, table_name), primary_path in sorted(primaries.items()):
        entry = {
            "path": relative_forward(primary_path, repo_root),
            "category": category,
            "table_name": table_name,
            "model_class": MODEL_CLASS_BY_TABLE[table_name],
            "content_sha256": sha256_hex(primary_path),
            "bytes": primary_path.stat().st_size,
            "has_extra": (category, table_name) in extras,
        }
        if entry["has_extra"]:
            extra_path = extras[(category, table_name)]
            entry["extra_path"] = relative_forward(extra_path, repo_root)
            entry["extra_sha256"] = sha256_hex(extra_path)
            entry["extra_bytes"] = extra_path.stat().st_size
        files.append(entry)

    return {
        "version": INDEX_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit_sha": git_commit_sha(repo_root),
        "count": len(files),
        "files": files,
    }


def serialize(index: dict) -> str:
    """Serialize the index to a deterministic JSON string with trailing newline."""
    return json.dumps(index, indent=2, sort_keys=True) + "\n"


def content_equals(a: dict, b: dict) -> bool:
    """Compare two index dicts ignoring generated_at and commit_sha."""
    ignored = {"generated_at", "commit_sha"}
    a_stable = {k: v for k, v in a.items() if k not in ignored}
    b_stable = {k: v for k, v in b.items() if k not in ignored}
    return a_stable == b_stable


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed index matches the tree; exit 1 if stale",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="override the repo root (default: the parent of the scripts/ directory)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root or Path(__file__).resolve().parent.parent
    index_path = repo_root / "data" / f"v{DATA_VERSION}" / INDEX_FILENAME

    new_index = build_index(repo_root)
    new_text = serialize(new_index)

    if args.check:
        if not index_path.is_file():
            print(
                f"error: {relative_forward(index_path, repo_root)} is missing",
                file=sys.stderr,
            )
            return 1
        try:
            old_index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(
                f"error: {relative_forward(index_path, repo_root)} is not valid JSON: {e}",
                file=sys.stderr,
            )
            return 1
        if not content_equals(old_index, new_index):
            print(
                f"error: {relative_forward(index_path, repo_root)} is out of sync with the tree.",
                file=sys.stderr,
            )
            print(
                "run `python scripts/generate_index.py` locally and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {relative_forward(index_path, repo_root)} is in sync ({new_index['count']} entries)")
        return 0

    index_path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = index_path.read_text(encoding="utf-8") if index_path.is_file() else None
    if existing_text is not None:
        try:
            existing_index = json.loads(existing_text)
        except json.JSONDecodeError:
            existing_index = None
        if existing_index is not None and content_equals(existing_index, new_index):
            print(
                f"ok: {relative_forward(index_path, repo_root)} already in sync "
                f"({new_index['count']} entries), not rewriting"
            )
            return 0

    # write_bytes forces LF line endings on all platforms (write_text on
    # Windows would translate \n to \r\n, producing a file that differs from
    # what Linux CI writes and triggering spurious git CRLF warnings).
    index_path.write_bytes(new_text.encode("utf-8"))
    print(
        f"wrote {relative_forward(index_path, repo_root)} "
        f"({new_index['count']} entries, {len(new_text)} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
