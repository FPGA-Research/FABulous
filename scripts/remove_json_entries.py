#!/usr/bin/env python3
"""
Simple script to remove matching log lines from a JSON file's string entries.
Usage: ./scripts/remove_json_entries.py <path> [--inplace]

It creates a backup when --inplace is used: <path>.bak

It removes lines that match:
- Errors have occurred while loading the design configuration file.
- Unknown key 'FABULOUS_*' provided.

The script walks the JSON structure and for every string value, removes those lines.
"""

import json
import sys
from pathlib import Path

key_to_remove = [
    "FABULOUS_TILE_SPACING",
    "FABULOUS_TILE_SIZES",
    # "FABULOUS_MANUAL_PINS",
    "FABULOUS_MACROS_SETTINGS",
    # "FABULOUS_HALO_SPACING",
    "FABULOUS_FABRIC",
    # "FABULOUS_SPEF_CORNERS",
]


def main():
    if len(sys.argv) < 2:
        print("Usage: remove_json_entries.py <file> [--inplace]")
        sys.exit(2)
    path = Path(sys.argv[1])
    inplace = "--inplace" in sys.argv[2:]
    data = json.loads(path.read_text())
    for key in key_to_remove:
        if key in data:
            del data[key]
    if inplace:
        bak = path.with_suffix(path.suffix + ".bak")
        path.rename(bak)
        path.write_text(json.dumps(data, indent=2))
        print(f"Wrote cleaned file to {path}, backup at {bak}")
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
