"""Tests for fabric generation with custom fabric names."""

from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import ConfigBitMode
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_fabric import generateFabric


def test_generate_fabric_uses_fabric_name(mocker: MockerFixture) -> None:
    """GenerateFabric should use fabric.name as the module name."""
    fabric = mocker.create_autospec(Fabric)
    fabric.name = "test_fabric"
    fabric.tile = []
    fabric.configBitMode = ConfigBitMode.FLIPFLOP_CHAIN
    fabric.maxFramesPerCol = 20
    fabric.frameBitsPerRow = 32
    fabric.numberOfRows = 0
    fabric.numberOfColumns = 0

    writer = mocker.create_autospec(CodeGenerator)

    generateFabric(writer, fabric)

    writer.addHeader.assert_called_once_with("test_fabric")
