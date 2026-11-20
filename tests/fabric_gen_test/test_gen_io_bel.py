"""Tests for generating Gen_IO BELs."""

from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import IO, HDLType
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_generator.gen_fabric.fabric_automation import genIOBel
from fabulous.fabulous_settings import init_context


@pytest.mark.parametrize(
    "gen_ios",
    [
        pytest.param(
            [
                Gen_IO("A", 2, IO.OUTPUT),
                Gen_IO("B", 1, IO.INPUT, clocked=True),
                Gen_IO("D", 1, IO.INPUT, clockedComb=True),
            ],
            id="io",
        ),
        pytest.param(
            [Gen_IO("C", 2, IO.OUTPUT, configBit=2, configAccess=True)],
            id="config_access",
        ),
    ],
)
def test_vhdl_gen_io_bel_matches_verilog(
    project_factory: Callable[..., Path], gen_ios: list[Gen_IO]
) -> None:
    """A VHDL Gen_IO BEL parses back to the same BEL as the Verilog one.

    The VHDL generator writes the FABulous directives as native attributes, which
    is the only form the BEL parser reads.
    """
    bels = {}
    for lang, suffix in [(HDLType.VERILOG, ".v"), (HDLType.VHDL, ".vhdl")]:
        project_dir = project_factory(lang=lang, name=f"project_{lang.value}")
        init_context(project_dir)
        bels[lang] = genIOBel(gen_ios, project_dir / "Tile" / f"GenIO{suffix}")

    verilog, vhdl = bels[HDLType.VERILOG], bels[HDLType.VHDL]
    assert vhdl.belFeatureMap == verilog.belFeatureMap
    for ports in [
        "input_ports",
        "output_ports",
        "external_input_ports",
        "external_output_ports",
    ]:
        assert [p.serialize() for p in getattr(vhdl, ports)] == [
            p.serialize() for p in getattr(verilog, ports)
        ], ports
    assert vhdl.sharedPort == verilog.sharedPort
    assert vhdl.configBit == verilog.configBit
