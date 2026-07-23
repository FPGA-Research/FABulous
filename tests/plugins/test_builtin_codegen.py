"""The built-in code-generator plugin registers Verilog and VHDL."""

from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_generator.code_generator import plugin
from fabulous.plugins.manager import PluginManager


def test_builtin_codegen_registers_verilog_and_vhdl() -> None:
    manager = PluginManager()
    manager.pm.register(plugin, name="builtin_codegen")
    manager.build_registries()
    assert manager.make_writer(HDLType.VERILOG).file_extension == ".v"
    assert manager.make_writer(HDLType.VHDL).file_extension == ".vhdl"
