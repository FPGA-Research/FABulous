"""The writer's fileExtension is a class attribute, not type-sniffed."""

from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)


def test_verilog_file_extension() -> None:
    assert VerilogCodeGenerator.fileExtension == ".v"


def test_vhdl_file_extension() -> None:
    assert VHDLCodeGenerator.fileExtension == ".vhdl"
