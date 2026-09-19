#!/usr/bin/env python3
"""Keep the committed renders of a draw.io diagram in step with its source.

Run as a pre-commit hook over the `.drawio` files in a commit. A diagram whose renders
are already current costs nothing, so this is a no-op on every machine that is not
editing diagrams -- including CI, which has no draw.io and needs none.

When a diagram is new or has changed, the renders are regenerated and staged alongside
it, because a commit carrying a diagram without its renders builds nowhere else.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "docs" / "source" / "_ext"))

from drawio_render import (  # noqa: E402
    CACHE_DIR_NAME,
    OVERRIDES_SUFFIX,
    DrawioError,
    render_diagram,
)


def _diagrams(argv: list[str]) -> list[Path]:
    """Reduce the changed files to the diagrams they belong to.

    A diagram's dark-mode colour table is matched by the hook too, since it
    changes the render, but it is the diagram that gets rendered.

    Parameters
    ----------
    argv : list[str]
        Paths as pre-commit passes them.

    Returns
    -------
    list[Path]
        The `.drawio` files to render, in order, without repeats.
    """
    diagrams = []
    for argument in argv:
        path = Path(argument)
        if path.name.endswith(OVERRIDES_SUFFIX):
            stem = path.name[: -len(OVERRIDES_SUFFIX)]
            path = path.with_name(f"{stem}.drawio")
        if path not in diagrams:
            diagrams.append(path)
    return diagrams


def _stage(cache_dir: Path) -> None:
    """Stage everything the render just changed in a cache directory.

    Parameters
    ----------
    cache_dir : Path
        The `_drawio_cache` directory holding the new renders.

    Raises
    ------
    DrawioError
        If the renders could not be staged.
    """
    result = subprocess.run(  # noqa: S603
        ["git", "add", "--all", "--", str(cache_dir)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DrawioError(f"could not stage {cache_dir}: {result.stderr.strip()}")


def main(argv: list[str]) -> int:
    """Render every diagram named on the command line that needs it.

    Parameters
    ----------
    argv : list[str]
        Paths to `.drawio` files and their colour tables, as pre-commit passes
        them.

    Returns
    -------
    int
        0 if every diagram has current, staged renders.
    """
    rendered = []
    for source in _diagrams(argv):
        try:
            renders, ran = render_diagram(source)
            if ran:
                _stage(source.parent / CACHE_DIR_NAME)
        except DrawioError as error:
            print(f"{source}: {error}", file=sys.stderr)
            return 1
        if ran:
            rendered.append((source, renders))

    for source, renders in rendered:
        names = ", ".join(sorted(path.name for path in renders.values()))
        print(f"{source}: rendered and staged {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
