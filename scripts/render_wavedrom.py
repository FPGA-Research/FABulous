#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["wavedrom==2.0.3.post3"]
# ///
"""Render a WaveJSON timing diagram to an SVG.

The Sphinx build renders the WaveJSON sources under `docs/` on its own through
`sphinxcontrib.wavedrom`, so nothing in the documentation depends on this script.
It exists to preview a diagram without paying for a full docs build:

    uv run scripts/render_wavedrom.py docs/source/user_guide/building_doc/figs/bitbang1.json /tmp/preview.svg

The output path is explicit so a preview never lands in the source tree. Each
source also pastes straight into https://wavedrom.com/editor.html.
"""

import sys
from pathlib import Path

import wavedrom


def main(argv: list[str]) -> None:
    """Render a WaveJSON source to an SVG.

    Parameters
    ----------
    argv : list[str]
        The WaveJSON source path followed by the SVG output path.

    Raises
    ------
    SystemExit
        If the two paths are not both given.
    """
    if len(argv) != 2:
        raise SystemExit(f"usage: {Path(__file__).name} <wavejson> <output.svg>")

    source, target = Path(argv[0]), Path(argv[1])
    target.write_text(wavedrom.render(source.read_text()).tostring() + "\n")
    print(f"{source} -> {target}")


if __name__ == "__main__":
    main(sys.argv[1:])
