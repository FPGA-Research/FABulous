"""Tests for the CLOCKED_MUX wiring of generated GEN_IO BELs."""

import re
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import IO, MultiplexerStyle
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_generator.gen_fabric import fabric_automation

GEN_IOS = [
    Gen_IO("P", 1, IO.OUTPUT, configBit=1, clockedMux=True),
    Gen_IO("R", 2, IO.OUTPUT, configBit=2, clockedMux=True),
    Gen_IO("A", 1, IO.INPUT),
]

# Patterns for the selector of each multiplexer, giving (sink, config bit).
SELECT_PATTERNS = {
    (MultiplexerStyle.CUSTOM, ".v"): (
        r"cus_mux21 inst_cus_mux21_\w+ \(.*?\.S\(ConfigBits\[(?P<bit>\d+)\]\),"
        r"\s*\.X\((?P<sink>\w+)\)"
    ),
    (MultiplexerStyle.CUSTOM, ".vhdl"): (
        r"inst_cus_mux21_\w+ : cus_mux21.*?S => ConfigBits\((?P<bit>\d+)\),"
        r"\s*X => (?P<sink>\w+)"
    ),
    (MultiplexerStyle.GENERIC, ".v"): (
        r"assign (?P<sink>\w+) = ConfigBits\[(?P<bit>\d+)\] \?"
    ),
    (MultiplexerStyle.GENERIC, ".vhdl"): (
        r"(?P<sink>\w+) <= \w+ when \(ConfigBits\((?P<bit>\d+)\) = '0'\)"
    ),
}

# Pattern for a plain assignment from another signal.
DIRECT_PATTERNS = {
    ".v": r"^assign (?P<sink>\w+) = (?P<source>\w+);$",
    ".vhdl": r"^(?P<sink>\w+) <= (?P<source>\w+) after 0 ps;$",
}


@pytest.fixture
def gen_io_text(
    tmp_path: Path, mocker: MockerFixture, request: pytest.FixtureRequest
) -> str:
    """Generate the GEN_IO BEL and return its HDL text."""
    style, suffix = request.param
    # Only the generated text is checked, so skip reading it back with Yosys.
    mocker.patch.object(fabric_automation, "parseBelFile")
    mocker.patch.object(fabric_automation, "addBelsToPrim")
    context = mocker.patch.object(fabric_automation, "get_context").return_value
    context.proj_dir = tmp_path
    (tmp_path / "user_design").mkdir()
    bel_path = tmp_path / f"GenIO{suffix}"
    fabric_automation.genIOBel(GEN_IOS, bel_path, multiplexerStyle=style)
    return bel_path.read_text()


CASES = [
    pytest.param(key, id=f"{key[0].name.lower()}{key[1]}") for key in SELECT_PATTERNS
]


@pytest.mark.parametrize("gen_io_text", CASES, indirect=True)
def test_clocked_mux_is_the_only_driver(
    gen_io_text: str, request: pytest.FixtureRequest
) -> None:
    """A CLOCKED_MUX output is driven by its multiplexer only."""
    suffix = request.node.callspec.params["gen_io_text"][1]
    direct = {
        m["sink"]: m["source"]
        for m in re.finditer(DIRECT_PATTERNS[suffix], gen_io_text, re.MULTILINE)
    }
    assert "P" not in direct
    assert "R0" not in direct
    assert "R1" not in direct
    # A plain GEN_IO keeps its direct assignment.
    assert direct["A_top"] == "A"


@pytest.mark.parametrize("gen_io_text", CASES, indirect=True)
def test_clocked_mux_uses_its_own_config_bit(
    gen_io_text: str, request: pytest.FixtureRequest
) -> None:
    """Each CLOCKED_MUX pin is selected by its own config bit, in order."""
    key = request.node.callspec.params["gen_io_text"]
    selects = {
        m["sink"]: int(m["bit"])
        for m in re.finditer(SELECT_PATTERNS[key], gen_io_text, re.DOTALL)
    }
    assert selects == {"P": 0, "R0": 1, "R1": 2}
