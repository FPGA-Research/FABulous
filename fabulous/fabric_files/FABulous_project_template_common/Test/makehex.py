#!/usr/bin/env python3
"""Convert a binary file to hex format for memory initialization.

This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this
software, either in source code form or as a compiled binary, for any purpose,
commercial or non-commercial, and by any means.
"""

import argparse
import os
from pathlib import Path


def validate_path(path_str, must_exist=False):
    path = Path(path_str).resolve()
    if ".." in path.parts or not path.is_relative_to(Path.cwd().root if os.name == "nt" else "/"):
        raise ValueError(f"Invalid path: {path_str}")
    if must_exist and not path.exists():
        raise ValueError(f"File does not exist: {path_str}")
    return path


def main():
    parser = argparse.ArgumentParser(description="Convert a binary file to hex format for memory initialization.")
    parser.add_argument("binfile", help="Input binary file path")
    parser.add_argument("nbytes", type=int, help="Number of bytes to output")
    parser.add_argument("outfile", help="Output hex file path")
    args = parser.parse_args()

    if args.nbytes < 0:
        parser.error("nbytes must be non-negative")

    binfile = validate_path(args.binfile, must_exist=True)
    outfile = validate_path(args.outfile)

    with binfile.open("rb") as f:
        bindata = f.read()

    if len(bindata) > args.nbytes:
        parser.error(f"Binary file ({len(bindata)} bytes) exceeds nbytes ({args.nbytes})")

    with outfile.open("w") as f:
        for i in range(args.nbytes):
            if i < len(bindata):
                print(f"{bindata[i]:02x}", file=f)
            else:
                print("0", file=f)


if __name__ == "__main__":
    main()
