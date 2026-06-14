"""Tests for architecture synthesizer flow helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)


def test_write_routingmodel_bitreamspec_uses_graph_routing_model(
    tmp_path: Path,
) -> None:
    """Write routing metadata through the attached graph-backed PnR model."""
    synthesizer = _RoutingMetadataSynthesizer()
    synthesizer.attach_fabulous_api(_FakeFab())  # type: ignore[arg-type]

    metadata_dir = synthesizer.write_routingmodel_bitreamspec(tmp_path / ".FABulous")

    assert (metadata_dir / "pips.txt").read_text(encoding="utf-8") == ("# graph pips\n")
    assert (metadata_dir / "bel.txt").read_text(encoding="utf-8") == "# graph bel\n"
    assert (metadata_dir / "bel.v2.txt").read_text(encoding="utf-8") == (
        "# graph bel v2\n"
    )
    assert (metadata_dir / "template.pcf").read_text(encoding="utf-8") == (
        "# graph template pcf\n"
    )
    assert (metadata_dir / "bitStreamSpec.bin").exists()
    assert (metadata_dir / "bitStreamSpec.csv").read_text(encoding="utf-8") == (
        "X0Y0\nFEATURE,{}\n"
    )


def test_write_switch_matrix_pattern_image_uses_fpga_model(
    tmp_path: Path,
) -> None:
    """Write a switch-matrix image from the attached PnR model."""
    synthesizer = _RoutingMetadataSynthesizer()
    synthesizer.attach_fabulous_api(_FakeFab())  # type: ignore[arg-type]

    result = synthesizer.write_switch_matrix_pattern_image(
        "TEST_TILE",
        tmp_path / "test_tile.png",
        mode="binary",
    )

    assert result.image_path.exists()
    assert result.labels_path is not None
    assert result.labels_path.exists()
    assert result.active_pips == 1


class _RoutingMetadataSynthesizer(ArchitectureSynthesizer):
    """Concrete synthesizer with a fake graph-backed PnR model."""

    def generate_fpga_model(self) -> None:
        """Attach a fake PnR model that writes routing metadata."""
        self.fpga_model = _FakePnRModel()  # type: ignore[assignment]

    def run_flow(self) -> None:
        """No-op flow entry point for tests."""


class _FakePnRModel:
    """Small graph-backed routing-model writer test double."""

    def switch_matrix(self, tile_name: str) -> _FakeSwitchMatrix:
        """Return a fake switch matrix for image-rendering tests.

        Parameters
        ----------
        tile_name : str
            Tile name to fetch.

        Returns
        -------
        _FakeSwitchMatrix
            Small fake switch-matrix object.

        Raises
        ------
        ValueError
            If the requested tile name is not known.
        """
        if tile_name != "TEST_TILE":
            raise ValueError(f"Unknown fake tile: {tile_name}")
        return _FakeSwitchMatrix()

    def write_routing_model(self, path: Path | str | None = None) -> None:
        """Write fake graph routing metadata.

        Parameters
        ----------
        path : Path | str | None
            Destination metadata directory.

        Raises
        ------
        ValueError
            If no output path is provided.
        """
        if path is None:
            raise ValueError("test fake requires an explicit metadata path")

        metadata_dir = Path(path)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        (metadata_dir / "pips.txt").write_text("# graph pips\n", encoding="utf-8")
        (metadata_dir / "bel.txt").write_text("# graph bel\n", encoding="utf-8")
        (metadata_dir / "bel.v2.txt").write_text(
            "# graph bel v2\n",
            encoding="utf-8",
        )
        (metadata_dir / "template.pcf").write_text(
            "# graph template pcf\n",
            encoding="utf-8",
        )


class _FakeSwitchMatrix:
    """Small switch-matrix object with the graph-facing matrix attribute."""

    rows = ["ROW0", "ROW1"]
    columns = ["COL0", "COL1"]
    matrix = [[0, 1], ["#", 0]]


class _FakeFab:
    """Small fake FABulous API for metadata-helper tests."""

    def genRoutingModel(self) -> tuple[str, str, str, str]:  # noqa: N802
        """Fail if synthesizer code still regenerates routing metadata.

        Returns
        -------
        tuple[str, str, str, str]
            Unused routing-model tuple; this fake always raises instead.

        Raises
        ------
        AssertionError
            Always raised; tests expect graph-backed routing metadata.
        """
        raise AssertionError("routing metadata must come from fpga_model")

    def genBitStreamSpec(self) -> dict[str, Any]:  # noqa: N802
        """Return a minimal bitstream spec object.

        Returns
        -------
        dict[str, Any]
            Minimal bitstream spec accepted by the metadata writer.
        """
        return {"TileSpecs": {"X0Y0": {"FEATURE": {}}}}
