#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_TILE_DIR = REPO_ROOT / "demo" / "Tile"
TEMPLATE_TILE_DIR = (
    REPO_ROOT
    / "fabulous"
    / "fabric_files"
    / "FABulous_project_template_common"
    / "Tile"
)


def sync_tile_configs(dry_run: bool) -> int:
    demo_configs = sorted(DEMO_TILE_DIR.glob("*/gds_config.yaml"))
    if not demo_configs:
        raise FileNotFoundError(
            f"No tile gds_config.yaml files found in {DEMO_TILE_DIR}"
        )

    updated = 0
    unchanged = 0

    for demo_config in demo_configs:
        tile_name = demo_config.parent.name
        template_config = TEMPLATE_TILE_DIR / tile_name / "gds_config.yaml"

        if not template_config.is_file():
            raise FileNotFoundError(
                f"Missing matching template config for tile '{tile_name}': {template_config}"
            )

        demo_content = demo_config.read_text(encoding="utf-8")
        template_content = template_config.read_text(encoding="utf-8")

        if demo_content == template_content:
            unchanged += 1
            print(f"UNCHANGED {tile_name}")
            continue

        updated += 1
        print(f"UPDATE    {tile_name}")
        if not dry_run:
            template_config.write_text(demo_content, encoding="utf-8")

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(
        f"\n{mode} summary: updated={updated}, unchanged={unchanged}, total={len(demo_configs)}"
    )
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync full demo tile gds_config.yaml files into FABulous template tile configs."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    args = parser.parse_args()

    sync_tile_configs(dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
