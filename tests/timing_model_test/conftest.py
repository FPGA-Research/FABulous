"""Fixtures shared by the timing model tests."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_model.netlist import NetlistIndex
from fabulous.fabulous_settings import get_context

type ReadNetlist = Callable[[str | Path, str], NetlistIndex]


@pytest.fixture
def read_netlist(tmp_path: Path) -> ReadNetlist:
    """Index a structural Verilog netlist, given as text or a file, with Yosys.

    The second argument names the top module. Skips when Yosys is unavailable.
    """
    if shutil.which(str(get_context().yosys_path)) is None:
        pytest.skip("yosys not on PATH; netlist indexing needs the Nix toolchain")

    def _read(source: str | Path, top: str) -> NetlistIndex:
        if isinstance(source, str):
            path = tmp_path / f"{top}.v"
            path.write_text(source)
            source = path
        return NetlistIndex.read(source, top=top)

    return _read
