"""Assemble a new project from a registered fabric and its tile library.

`fabulous_fabrics.fabrics` and `fabulous_tiles.tile_libraries` find fabrics and tile
libraries from their packages' directory layout, so a project builds the same from
a wheel, a uv git source or the Nix store. Every file is copied into the project,
because parsing a VHDL BEL writes `.v` and `.json` files next to its source and an
installed package can be read-only.
"""

import shutil
from pathlib import Path

from fabulous_fabrics import FabricSource
from fabulous_tiles import Language, TileLibrary

from fabulous.fabric_definition.define import HDLType

DEFAULT_FABRIC = "fabulous"


def to_language(lang: HDLType) -> Language:
    """Return the asset-package language for `lang`.

    Parameters
    ----------
    lang : HDLType
        The project language.

    Returns
    -------
    Language
        The matching `fabulous_tiles` language.

    Raises
    ------
    ValueError
        If `lang` is neither Verilog nor VHDL.
    """
    match lang:
        case HDLType.VERILOG:
            return Language.VERILOG
        case HDLType.VHDL:
            return Language.VHDL
        case _:
            raise ValueError(
                f"Fabrics and tile libraries ship Verilog and VHDL only, not {lang}."
            )


def _copy_writable(src: Path, dest: Path) -> None:
    """Copy file contents only, so a read-only source yields a writable copy."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


def _copy_into_tile(src: Path, dest: Path, sources: dict[Path, Path]) -> None:
    """Copy `src` to `dest` unless a different source already landed at `dest`.

    Parameters
    ----------
    src : Path
        The file to copy.
    dest : Path
        The destination under the project's `Tile/`.
    sources : dict[Path, Path]
        The source already copied to each destination, updated in place.

    Raises
    ------
    FileExistsError
        If `dest` already holds a copy of a file whose bytes differ from `src`.
    """
    if dest in sources and sources[dest].read_bytes() != src.read_bytes():
        raise FileExistsError(
            f"{dest} would hold both {sources[dest]} and {src}, which differ. "
            "Rename one of them."
        )
    sources[dest] = src
    _copy_writable(src, dest)


def copy_fabric(project_dir: Path, fabric: FabricSource, lang: HDLType) -> None:
    """Copy the project skeleton of `fabric` for `lang` into `project_dir`.

    A language other than Verilog or VHDL, or one the fabric ships no skeleton for,
    raises `ValueError`.

    Parameters
    ----------
    project_dir : Path
        The project root.
    fabric : FabricSource
        The fabric to copy.
    lang : HDLType
        The project language.
    """
    for rel, src in fabric.files(to_language(lang)).items():
        _copy_writable(src, project_dir / rel)


def copy_tile_library(project_dir: Path, library: TileLibrary, lang: HDLType) -> None:
    """Copy `library` into `project_dir/Tile` with tile-local BEL sources.

    Files directly in the library root are library metadata and are skipped. Each
    `BEL,` row is rewritten to `./<file name>`, and the primitive source the tile
    library resolved for it is copied next to the tile CSV. Two files with different
    bytes that would land at the same path raise `FileExistsError`.

    Parameters
    ----------
    project_dir : Path
        The project root.
    library : TileLibrary
        The tile library to copy.
    lang : HDLType
        The project language, which selects each BEL's primitive source.

    Raises
    ------
    ValueError
        If `lang` is neither Verilog nor VHDL, a BEL has no source for it, or a CSV
        that is no tile of the library holds a `BEL,` row.
    """
    language = to_language(lang)
    bel_sources = {
        tile.csv: {bel.row: bel.source(language) for bel in tile.bels}
        for tile in library.values()
    }
    sources: dict[Path, Path] = {}
    for src in sorted(library.root.rglob("*")):
        if not src.is_file() or src.parent == library.root:
            continue
        dest = project_dir / "Tile" / src.relative_to(library.root)
        if src.suffix != ".csv":
            _copy_into_tile(src, dest, sources)
            continue
        out: list[str] = []
        with src.open(newline="") as f:
            lines = f.read().splitlines(keepends=True)
        for line in lines:
            body = line.rstrip("\r\n")
            fields = body.split(",")
            if fields[0] != "BEL":
                out.append(line)
                continue
            if src not in bel_sources:
                raise ValueError(
                    f"{src} holds a BEL row but is no tile of library {library.name}."
                )
            bel_src = bel_sources[src][fields[1].strip()]
            _copy_into_tile(bel_src, dest.parent / bel_src.name, sources)
            fields[1] = f"./{Path(fields[1]).name}"
            out.append(",".join(fields) + line[len(body) :])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("".join(out), newline="")
