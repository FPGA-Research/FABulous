"""Switch-matrix visualization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw

SwmImageMode = Literal["heat", "binary"]
MatrixValue = object
SwitchMatrixMapping = Mapping[str, Mapping[str, MatrixValue]]
SwitchMatrixTable = list[list[MatrixValue]]
SwitchMatrixInput = object


@dataclass(frozen=True)
class SwmImageResult:
    """Files written by a switch-matrix image render."""

    image_path: Path
    labels_path: Path | None
    rows: int
    columns: int
    active_pips: int


def gen_swm_pattern_image(
    switch_matrix: SwitchMatrixInput,
    out_path: str | Path,
    *,
    mode: SwmImageMode = "heat",
    pixel_size: int = 1,
    grid_every: int = 0,
    write_labels: bool = True,
    labels_path: str | Path | None = None,
    max_value: float | None = None,
    zero_color: tuple[int, int, int] = (246, 251, 255),
    binary_color: tuple[int, int, int] = (0, 0, 0),
) -> SwmImageResult:
    """Render a switch matrix as a PNG image.

    Parameters
    ----------
    switch_matrix : SwitchMatrixInput
        Either a graph ``RoutingSwitchMatrix`` object, a matrix in
        ``matrix[row_wire][column_wire] = value`` form, or a raw 2D list.
        Zero, empty, and ``"#"`` entries are rendered as inactive PIPs.
    out_path : str | Path
        PNG path to write.
    mode : SwmImageMode
        ``"heat"`` maps low non-zero values to blue and high values through
        red toward black. ``"binary"`` renders every non-zero entry black.
    pixel_size : int
        Output pixel size for each matrix entry. Values greater than one use
        nearest-neighbor scaling to keep PIPs crisp.
    grid_every : int
        Draw a subtle grid every N matrix rows/columns after scaling. Use zero
        to disable the grid.
    write_labels : bool
        Whether to write a TSV sidecar mapping pixel indices to wire names.
    labels_path : str | Path | None
        Optional explicit labels sidecar path. If ``None``, use
        ``<out_path>.labels.tsv``.
    max_value : float | None
        Optional heat-map maximum. If ``None``, the largest non-zero numeric
        value in the matrix is used.
    zero_color : tuple[int, int, int]
        RGB color for inactive matrix entries.
    binary_color : tuple[int, int, int]
        RGB color for active entries in ``"binary"`` mode.

    Returns
    -------
    SwmImageResult
        Metadata for the generated image and optional label sidecar.

    Raises
    ------
    ValueError
        If ``mode`` is unknown or sizing arguments are invalid.
    """
    if mode not in ("heat", "binary"):
        raise ValueError(f"Unsupported switch-matrix image mode: {mode!r}")
    if pixel_size < 1:
        raise ValueError("pixel_size must be >= 1")
    if grid_every < 0:
        raise ValueError("grid_every must be >= 0")

    image_path = Path(out_path)
    row_names, column_names, value_rows = _normalize_matrix(switch_matrix)
    numeric_values = [
        numeric
        for row in value_rows
        for value in row
        if (numeric := _active_numeric_value(value)) is not None
    ]

    value_max = max_value
    if value_max is None:
        value_max = max(numeric_values, default=1.0)
    if value_max <= 0.0:
        value_max = 1.0

    width = max(len(column_names), 1)
    height = max(len(row_names), 1)
    image = Image.new("RGB", (width, height), zero_color)
    pixels = image.load()

    for y, _row_name in enumerate(row_names):
        row = value_rows[y]
        for x, _column_name in enumerate(column_names):
            numeric = _active_numeric_value(row[x] if x < len(row) else None)
            if numeric is None:
                continue
            if mode == "binary":
                pixels[x, y] = binary_color
            else:
                pixels[x, y] = _heat_color(numeric / value_max)

    if pixel_size > 1:
        image = image.resize(
            (width * pixel_size, height * pixel_size),
            resample=Image.Resampling.NEAREST,
        )

    if grid_every > 0 and pixel_size > 1:
        _draw_grid(image, grid_every=grid_every, pixel_size=pixel_size)

    image_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(image_path)

    written_labels_path = None
    if write_labels:
        written_labels_path = (
            Path(labels_path)
            if labels_path is not None
            else image_path.with_suffix(f"{image_path.suffix}.labels.tsv")
        )
        _write_labels(written_labels_path, row_names, column_names)

    return SwmImageResult(
        image_path=image_path,
        labels_path=written_labels_path,
        rows=len(row_names),
        columns=len(column_names),
        active_pips=len(numeric_values),
    )


def _normalize_matrix(
    switch_matrix: SwitchMatrixInput,
) -> tuple[list[str], list[str], list[list[MatrixValue]]]:
    """Return row labels, column labels, and a rectangular value table."""
    if _looks_like_routing_switch_matrix(switch_matrix):
        rows = [str(row) for row in switch_matrix.rows]
        columns = [str(column) for column in switch_matrix.columns]
        values = [list(row) for row in switch_matrix.matrix]
        return rows, columns, _rectangular_values(values, len(columns))

    if isinstance(switch_matrix, Mapping):
        return _normalize_mapping_matrix(switch_matrix)

    values = [list(row) for row in switch_matrix]
    width = max((len(row) for row in values), default=0)
    rows = [f"row{index}" for index in range(len(values))]
    columns = [f"column{index}" for index in range(width)]
    return rows, columns, _rectangular_values(values, width)


def _looks_like_routing_switch_matrix(value: object) -> bool:
    """Return whether a value has the graph switch-matrix object shape."""
    return (
        hasattr(value, "rows")
        and hasattr(value, "columns")
        and hasattr(value, "matrix")
        and not isinstance(value, Mapping)
    )


def _normalize_mapping_matrix(
    switch_matrix: SwitchMatrixMapping,
) -> tuple[list[str], list[str], list[list[MatrixValue]]]:
    """Normalize a nested mapping matrix into a rectangular value table."""
    row_names = [str(row_name) for row_name in switch_matrix]
    seen_columns: set[str] = set()
    column_names: list[str] = []

    for row in switch_matrix.values():
        for raw_column_name in row:
            column_name = str(raw_column_name)
            if column_name in seen_columns:
                continue
            seen_columns.add(column_name)
            column_names.append(column_name)

    values = [
        [row.get(column_name) for column_name in column_names]
        for row in switch_matrix.values()
    ]

    return row_names, column_names, values


def _rectangular_values(
    values: list[list[MatrixValue]],
    width: int,
) -> list[list[MatrixValue]]:
    """Pad ragged matrix rows to a rectangular table."""
    return [row + [None] * (width - len(row)) for row in values]


def _active_numeric_value(value: MatrixValue) -> float | None:
    """Return a numeric active value, or ``None`` for inactive entries."""
    if value is None:
        return None
    if isinstance(value, str):
        clean = value.strip()
        if clean in ("", "0", "#"):
            return None
        try:
            numeric = float(clean)
        except ValueError:
            return 1.0
    else:
        try:
            numeric = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 1.0

    if numeric == 0.0:
        return None
    return numeric


def _heat_color(value: float) -> tuple[int, int, int]:
    """Map normalized heat values from blue through red toward black."""
    t = min(max(value, 0.0), 1.0)

    if t <= 0.5:
        local = t / 0.5
        return (
            int(45 + 175 * local),
            int(120 * (1.0 - local)),
            int(255 * (1.0 - local)),
        )

    local = (t - 0.5) / 0.5
    return (
        int(220 * (1.0 - local)),
        0,
        0,
    )


def _draw_grid(image: Image.Image, *, grid_every: int, pixel_size: int) -> None:
    """Draw subtle regular grid lines on a scaled matrix image."""
    draw = ImageDraw.Draw(image)
    grid_color = (210, 220, 230)
    width, height = image.size
    step = grid_every * pixel_size

    for x in range(step, width, step):
        draw.line((x, 0, x, height), fill=grid_color)
    for y in range(step, height, step):
        draw.line((0, y, width, y), fill=grid_color)


def _write_labels(
    labels_path: Path,
    row_names: list[str],
    column_names: list[str],
) -> None:
    """Write row and column label sidecar information."""
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["axis\tindex\tname\n"]
    lines.extend(f"row\t{index}\t{name}\n" for index, name in enumerate(row_names))
    lines.extend(
        f"column\t{index}\t{name}\n" for index, name in enumerate(column_names)
    )
    labels_path.write_text("".join(lines), encoding="utf-8")
