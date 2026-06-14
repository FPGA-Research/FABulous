"""Tests for switch-matrix image rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

from fabulous.fabric_cad.fabxplore.utils.swm_image import gen_swm_pattern_image

if TYPE_CHECKING:
    from pathlib import Path


def test_gen_swm_pattern_image_writes_binary_png_and_labels(tmp_path: Path) -> None:
    """Render active and inactive switch-matrix entries to image pixels."""
    matrix = {
        "ROW0": {"COL0": 0, "COL1": 1},
        "ROW1": {"COL0": "#", "COL1": "4"},
    }

    result = gen_swm_pattern_image(
        matrix,
        tmp_path / "swm.png",
        mode="binary",
        pixel_size=2,
        grid_every=0,
    )

    assert result.rows == 2
    assert result.columns == 2
    assert result.active_pips == 2
    assert result.image_path.exists()
    assert result.labels_path is not None
    assert result.labels_path.exists()

    image = Image.open(result.image_path)
    assert image.size == (4, 4)
    assert image.getpixel((0, 0)) == (246, 251, 255)
    assert image.getpixel((2, 0)) == (0, 0, 0)

    labels = result.labels_path.read_text(encoding="utf-8")
    assert "row\t0\tROW0\n" in labels
    assert "column\t1\tCOL1\n" in labels
