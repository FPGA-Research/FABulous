"""Tests for the `template.pcf` export produced by `gen_pcf_template`.

The template lists every constrainable I/O site so a user can copy the ones
they need into their own PCF. Each location must be written in the slash form
(`X0Y1/A`) that the nextpnr `fabulous` uarch actually accepts; the older
`Tile_X0Y1.A` naming is no longer valid.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_cad.gen_pcf_template import gen_pcf_template
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile


def make_bel(module: str, prefix: str, internal: list[tuple[str, IO]]) -> Bel:
    """Build a minimal BEL; only `name`, `prefix` and pins are populated."""
    return Bel(
        src=Path(f"{module}.v"),
        prefix=prefix,
        module_name=module,
        internal=internal,
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )


def make_tile(name: str, bels: list[Bel]) -> Tile:
    """Build a minimal Tile carrying only the BELs under test."""
    return Tile(
        name=name,
        ports=[],
        bels=bels,
        tileDir=Path(),
        switch_matrix=SwitchMatrix(matrix_file=Path(), connections={}),
        gen_ios=[],
        userCLK=False,
        pinOrderConfig={},
    )


@pytest.fixture
def io_fabric(make_fabric: Callable[..., Fabric]) -> Fabric:
    """A one-row fabric: a bidirectional I/O tile and a BRAM-input tile."""
    io_tile = make_tile(
        "IO",
        [
            make_bel(
                "IO_1_bidirectional_frame_config_pass",
                "A_",
                [("A_I", IO.INPUT), ("A_O", IO.OUTPUT)],
            )
        ],
    )
    bram_tile = make_tile(
        "BRAM",
        [
            make_bel(
                "InPass4_frame_config_mux",
                "RAM2FAB_D0_",
                [("RAM2FAB_D0_O0", IO.OUTPUT)],
            )
        ],
    )
    return make_fabric(tile=[[io_tile, bram_tile]])


def _template(fabric: Fabric) -> str:
    return gen_pcf_template(fabric)


def test_bidirectional_io_uses_letter_slot(io_fabric: Fabric) -> None:
    lines = _template(io_fabric).splitlines()
    assert "# set_io <net> X0Y0/A" in lines


def test_bram_io_uses_port_prefix_slot(io_fabric: Fabric) -> None:
    # InPass4/OutPass4 BELs are named by port prefix, not the letter.
    lines = _template(io_fabric).splitlines()
    assert "# set_io <net> X1Y0/RAM2FAB_D0" in lines


def test_no_stale_tile_dot_naming(io_fabric: Fabric) -> None:
    template = _template(io_fabric)
    # The old, unusable form was `set_io Tile_X0Y0_A Tile_X0Y0.A`.
    assert "Tile_X" not in template
    assert ".A" not in template
