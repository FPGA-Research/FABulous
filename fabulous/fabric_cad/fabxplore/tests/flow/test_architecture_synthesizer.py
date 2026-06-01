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


class _RoutingMetadataSynthesizer(ArchitectureSynthesizer):
    """Concrete synthesizer with a fake graph-backed PnR model."""

    def generate_fpga_model(self) -> None:
        """Attach a fake PnR model that writes routing metadata."""
        self.fpga_model = _FakePnRModel()  # type: ignore[assignment]

    def run_flow(self) -> None:
        """No-op flow entry point for tests."""


class _FakePnRModel:
    """Small graph-backed routing-model writer test double."""

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
