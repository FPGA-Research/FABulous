"""Built-in plugin registering the Verilog and VHDL code generators."""

from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.plugins import hookimpl
from fabulous.plugins.types import CodeGeneratorProvider


@hookimpl
def fabulous_register_code_generators() -> list[CodeGeneratorProvider]:
    """Register the built-in Verilog and VHDL code generators.

    Returns
    -------
    list[CodeGeneratorProvider]
        Providers for the Verilog and VHDL generators.
    """
    return [
        CodeGeneratorProvider(
            hdl_type=HDLType.VERILOG, factory=VerilogCodeGenerator, name="verilog"
        ),
        CodeGeneratorProvider(
            hdl_type=HDLType.VHDL, factory=VHDLCodeGenerator, name="vhdl"
        ),
    ]
