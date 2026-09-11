"""Render draw.io diagrams to the pair of SVGs the documentation embeds.

This is the half of the `drawio` extension that knows how to drive the draw.io CLI and
maintain the render cache. It deliberately imports nothing beyond the standard library,
so the pre-commit hook that regenerates diagrams can share it with the Sphinx directive
in `drawio.py` rather than growing its own copy of the same logic.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

CACHE_DIR_NAME = "_drawio_cache"
OVERRIDES_SUFFIX = ".dark.toml"
BINARY_ENV_VAR = "DRAWIO_BINARY"
MACOS_APP_BINARY = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")
DIGEST_LENGTH = 12
DEFAULT_BORDER = 12
DEFAULT_TIMEOUT = 120

# The light value of every ``light-dark()`` pair comes first, the dark value second.
VARIANT_INDEX = {"light": 0, "dark": 1}

# draw.io wraps each HTML label in a ``<switch>`` holding a ``<foreignObject>`` and, for
# viewers without SVG 1.1 extensibility, a base64 PNG of the same text plus a link
# telling the reader to open the file elsewhere. Browsers render the ``<foreignObject>``,
# so the fallback is dead weight worth roughly twenty times the rest of the file.
RASTER_FALLBACK = re.compile(r"<image[^>]*?/>")
LINK_FALLBACK = re.compile(r"<a\b[^>]*>\s*<text[^>]*>.*?</text>\s*</a>", re.DOTALL)

LIGHT_DARK_TOKEN = "light-dark("
AUTO_COLOUR_SCHEME = "color-scheme: light dark;"

HEX_COLOUR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
RGB_COLOUR = re.compile(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$")
# The light half of a pair, which is all the override table is keyed by. It is
# either a hex literal or an ``rgb()`` call, so the parentheses are bounded.
LIGHT_COLOUR = re.compile(
    r"light-dark\(\s*(#[0-9a-fA-F]{3,6}|rgb\([^)]*\))",
)

NO_BINARY_MESSAGE = (
    "{source} has no up-to-date render in {cache}, and draw.io was not found. Renders "
    "are committed so that Read the Docs and CI never need draw.io: whoever edits a "
    "diagram regenerates them. Install draw.io (or point drawio_binary_path / "
    "${env_var} at it), run `task docs-build`, and commit the result."
)


class DrawioError(Exception):
    """A diagram could not be rendered."""


def _normalise_source(raw: bytes) -> bytes:
    """Reduce a diagram source to the form its rendering actually depends on.

    draw.io saves without a trailing newline, and pre-commit's whitespace hooks add
    one the moment the file is committed. Hashing the bytes as written would let that
    rewrite invalidate renders that are still perfectly good, leaving a build with no
    draw.io to fail over a newline. None of the whitespace those hooks touch reaches
    the SVG, so it is normalised away before hashing.

    Parameters
    ----------
    raw : bytes
        The contents of a `.drawio` file.

    Returns
    -------
    bytes
        The same diagram with Unix line endings, no trailing whitespace on any line,
        and exactly one newline at the end.
    """
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return ("\n".join(lines).strip() + "\n").encode("utf-8")


def overrides_path(source: Path) -> Path:
    """Build the path of a diagram's dark-mode colour table.

    Parameters
    ----------
    source : Path
        The `.drawio` file the table belongs to.

    Returns
    -------
    Path
        Where the table lives, whether or not it exists.
    """
    return source.with_name(f"{source.stem}{OVERRIDES_SUFFIX}")


def _normalise_colour(value: str) -> str | None:
    """Reduce a CSS colour to lower-case `#rrggbb`, so colours compare equal.

    Parameters
    ----------
    value : str
        A colour as it appears in an SVG or an override table.

    Returns
    -------
    str | None
        The colour as `#rrggbb`, or None if it is in neither notation the
        override table can be keyed by.
    """
    text = value.strip()
    if match := RGB_COLOUR.fullmatch(text):
        channels = [int(channel) for channel in match.groups()]
        if any(channel > 255 for channel in channels):
            return None
        return "#{:02x}{:02x}{:02x}".format(*channels)
    if HEX_COLOUR.fullmatch(text):
        digits = text[1:].lower()
        if len(digits) == 3:
            digits = "".join(digit * 2 for digit in digits)
        return f"#{digits}"
    return None


def load_overrides(source: Path) -> dict[str, str]:
    """Read the dark-mode colours a diagram pins by hand.

    Parameters
    ----------
    source : Path
        The `.drawio` file whose table should be read.

    Returns
    -------
    dict[str, str]
        The dark colour to use for each light colour, both as `#rrggbb`. Empty
        if the diagram pins nothing.

    Raises
    ------
    DrawioError
        If the table is not readable TOML, or holds something that is not a
        colour on either side of a mapping.
    """
    path = overrides_path(source)
    if not path.is_file():
        return {}

    try:
        table = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise DrawioError(f"{path} is not valid TOML: {error}") from error

    overrides = {}
    for light, dark in table.items():
        key = _normalise_colour(light)
        value = _normalise_colour(dark) if isinstance(dark, str) else None
        if key is None or value is None:
            raise DrawioError(
                f"{path}: {light!r} = {dark!r} is not a mapping between two "
                "colours. Both sides must be #rgb, #rrggbb or rgb(r, g, b)."
            )
        overrides[key] = value
    return overrides


def source_digest(source: Path) -> str:
    """Hash a diagram source so its renders can be keyed by content.

    The dark-mode colour table is hashed alongside the diagram: it changes the
    render just as surely as the diagram does, and a render keyed by the diagram
    alone would survive an edit to the palette.

    Parameters
    ----------
    source : Path
        The `.drawio` file to hash.

    Returns
    -------
    str
        The leading hex characters of the SHA-256 digest of the normalised file.
    """
    normalised = _normalise_source(source.read_bytes())
    overrides = overrides_path(source)
    if overrides.is_file():
        normalised += _normalise_source(overrides.read_bytes())
    return hashlib.sha256(normalised).hexdigest()[:DIGEST_LENGTH]


def cache_path(source: Path, digest: str, variant: str) -> Path:
    """Build the path a rendered variant is cached at.

    Parameters
    ----------
    source : Path
        The `.drawio` file the render comes from.
    digest : str
        Digest of the source, as returned by `source_digest`.
    variant : str
        Either `light` or `dark`.

    Returns
    -------
    Path
        Where the rendered SVG for that variant lives.
    """
    return source.parent / CACHE_DIR_NAME / f"{source.stem}.{digest}.{variant}.svg"


def _find_binary(configured: str | None) -> Path | None:
    """Locate the draw.io CLI.

    A configured path is taken at its word: if it is not executable that is a
    misconfiguration to report, not a reason to look elsewhere.

    Parameters
    ----------
    configured : str | None
        An explicitly configured binary path, if there is one.

    Returns
    -------
    Path | None
        The draw.io binary, or None if the machine has no draw.io installed.

    Raises
    ------
    DrawioError
        If the configured path points at something that cannot be executed.
    """
    if configured:
        binary = Path(configured).expanduser()
        if not os.access(binary, os.X_OK):
            raise DrawioError(
                f"drawio_binary_path is set to {binary}, which is not executable."
            )
        return binary

    candidates = []
    from_env = os.environ.get(BINARY_ENV_VAR)
    if from_env:
        candidates.append(Path(from_env).expanduser())
    on_path = shutil.which("drawio")
    if on_path:
        candidates.append(Path(on_path))
    candidates.append(MACOS_APP_BINARY)

    for candidate in candidates:
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def _export_svg(binary: Path, source: Path, border: int, timeout: int) -> str:
    """Run the draw.io CLI over a diagram and return the exported SVG.

    The export asks for the `auto` colour scheme, which emits every colour as a CSS
    `light-dark()` pair. Both theme variants are then derived from this one export
    rather than paying for a second run of the (Electron-based, multi-second) CLI.

    Parameters
    ----------
    binary : Path
        The draw.io binary to run.
    source : Path
        The `.drawio` file to export.
    border : int
        Width of the border to leave around the diagram, in diagram units.
    timeout : int
        How long to wait for the export, in seconds.

    Returns
    -------
    str
        The exported SVG.

    Raises
    ------
    DrawioError
        If draw.io fails, times out, or writes no file.
    """
    with tempfile.TemporaryDirectory() as workdir:
        exported = Path(workdir) / f"{source.stem}.svg"
        command = [
            str(binary),
            "--no-sandbox",
            "--export",
            "--format",
            "svg",
            "--svg-theme",
            "auto",
            "--border",
            str(border),
            "--output",
            str(exported),
            str(source),
        ]
        try:
            result = subprocess.run(  # noqa: S603
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise DrawioError(
                f"draw.io timed out after {timeout}s exporting {source}. Raise "
                "drawio_export_timeout if the diagram is genuinely this large."
            ) from error

        if result.returncode != 0 or not exported.is_file():
            raise DrawioError(
                f"draw.io failed to export {source} (exit {result.returncode}).\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return exported.read_text(encoding="utf-8")


def _resolve_colour_scheme(
    svg: str, variant: str, overrides: dict[str, str] | None = None
) -> str:
    """Collapse every `light-dark()` pair in an SVG down to one theme's colour.

    Baking the colours in keeps the two variants independent of how the browser resolves
    `color-scheme`, which matters because Furo's theme toggle cannot reach inside an
    image, and because `light-dark()` needs a 2024-era browser to work at all.

    Parameters
    ----------
    svg : str
        An SVG exported with the `auto` colour scheme.
    variant : str
        Either `light` or `dark`.
    overrides : dict[str, str] | None
        Dark colours to use in place of the ones draw.io derived, keyed by the
        light colour they sit opposite. Ignored for the light variant.

    Returns
    -------
    str
        The SVG with a single colour per element.

    Raises
    ------
    DrawioError
        If a `light-dark()` call is malformed.
    """
    wanted = VARIANT_INDEX[variant]
    pinned = overrides if variant == "dark" and overrides else {}
    chunks = []
    cursor = 0

    while (start := svg.find(LIGHT_DARK_TOKEN, cursor)) != -1:
        chunks.append(svg[cursor:start])
        depth = 0
        separator = -1
        position = start + len(LIGHT_DARK_TOKEN)
        while position < len(svg):
            character = svg[position]
            if character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    break
                depth -= 1
            elif character == "," and depth == 0:
                separator = position
            position += 1

        if position == len(svg) or separator == -1:
            raise DrawioError(f"Malformed light-dark() call at offset {start}.")

        colours = (
            svg[start + len(LIGHT_DARK_TOKEN) : separator],
            svg[separator + 1 : position],
        )
        light = _normalise_colour(colours[0])
        chunks.append(pinned.get(light, colours[wanted].strip()))
        cursor = position + 1

    chunks.append(svg[cursor:])
    resolved = "".join(chunks)
    return resolved.replace(AUTO_COLOUR_SCHEME, f"color-scheme: {variant};", 1)


def _write_atomically(target: Path, content: str) -> None:
    """Write a render so that a concurrent reader never sees a half-written file.

    Sphinx reads documents in parallel when asked to, and two workers can reach the
    same diagram at once.

    Parameters
    ----------
    target : Path
        Where the content should end up.
    content : str
        The rendered SVG.
    """
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        delete=False,
    )
    with handle:
        handle.write(content)
    os.replace(handle.name, target)


def _prune_stale_renders(source: Path, digest: str) -> list[Path]:
    """Delete renders of a diagram left behind by earlier versions of its source.

    Parameters
    ----------
    source : Path
        The `.drawio` file whose renders are being pruned.
    digest : str
        Digest of the current source; renders keyed by anything else are stale.

    Returns
    -------
    list[Path]
        The renders that were removed.
    """
    current = {cache_path(source, digest, variant).name for variant in VARIANT_INDEX}
    removed = []
    for render in (source.parent / CACHE_DIR_NAME).glob(f"{source.stem}.*.svg"):
        if render.name not in current:
            render.unlink()
            removed.append(render)
    return removed


def render_diagram(
    source: Path,
    *,
    binary_path: str | None = None,
    border: int = DEFAULT_BORDER,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[dict[str, Path], bool]:
    """Return the rendered variants of a diagram, exporting them if need be.

    Parameters
    ----------
    source : Path
        The `.drawio` file to render.
    binary_path : str | None
        An explicitly configured draw.io binary, if there is one.
    border : int
        Width of the border to leave around the diagram, in diagram units.
    timeout : int
        How long to wait for an export, in seconds.

    Returns
    -------
    tuple[dict[str, Path], bool]
        The cached SVG for each of `light` and `dark`, and whether draw.io had to be
        run to produce them.

    Raises
    ------
    DrawioError
        If the renders are missing or stale and draw.io is not installed, or if
        the dark-mode colour table names a colour the diagram does not use.
    """
    digest = source_digest(source)
    targets = {
        variant: cache_path(source, digest, variant) for variant in VARIANT_INDEX
    }
    if all(target.is_file() for target in targets.values()):
        return targets, False

    cache_dir = source.parent / CACHE_DIR_NAME
    binary = _find_binary(binary_path)
    if binary is None:
        raise DrawioError(
            NO_BINARY_MESSAGE.format(
                source=source, cache=cache_dir, env_var=BINARY_ENV_VAR
            )
        )

    exported = _export_svg(binary, source, border, timeout)
    exported = LINK_FALLBACK.sub("", RASTER_FALLBACK.sub("", exported))

    overrides = load_overrides(source)
    themed = {
        _normalise_colour(match.group(1)) for match in LIGHT_COLOUR.finditer(exported)
    }
    if unused := sorted(set(overrides) - themed):
        raise DrawioError(
            f"{overrides_path(source)} pins {', '.join(unused)}, which "
            f"{source.name} does not use. A pin that matches nothing is a "
            "typo, or a leftover from a colour the diagram has since dropped."
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    for variant, target in targets.items():
        _write_atomically(
            target, _resolve_colour_scheme(exported, variant, overrides) + "\n"
        )
    _prune_stale_renders(source, digest)

    return targets, True
