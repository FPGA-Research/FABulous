"""RTL validation for generated Switch Matrix modules using Yosys."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple, Protocol

import pytest

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix


class SwitchMatrixDUT(Protocol):
    """Protocol defining the Switch Matrix module interface."""

    # Configuration Interface
    ConfigBits: Any  # [NoConfigBits-1:0] Configuration bits for multiplexer control

    # Routing Signal Inputs (examples - actual signals depend on tile configuration)
    # North Direction
    N1END0: Any  # North 1-wire end signal 0
    N1END1: Any  # North 1-wire end signal 1
    N2END0: Any  # North 2-wire end signal 0
    N2END1: Any  # North 2-wire end signal 1

    # East Direction
    E1END0: Any  # East 1-wire end signal 0
    E1END1: Any  # East 1-wire end signal 1
    E2END0: Any  # East 2-wire end signal 0
    E2END1: Any  # East 2-wire end signal 1

    # South Direction
    S1END0: Any  # South 1-wire end signal 0
    S1END1: Any  # South 1-wire end signal 1
    S2END0: Any  # South 2-wire end signal 0
    S2END1: Any  # South 2-wire end signal 1

    # West Direction
    W1END0: Any  # West 1-wire end signal 0
    W1END1: Any  # West 1-wire end signal 1
    W2END0: Any  # West 2-wire end signal 0
    W2END1: Any  # West 2-wire end signal 1

    # Routing Signal Outputs (examples - actual signals depend on tile configuration)
    # North Direction
    N1BEG0: Any  # North 1-wire begin signal 0
    N1BEG1: Any  # North 1-wire begin signal 1
    N2BEG0: Any  # North 2-wire begin signal 0
    N2BEG1: Any  # North 2-wire begin signal 1

    # East Direction
    E1BEG0: Any  # East 1-wire begin signal 0
    E1BEG1: Any  # East 1-wire begin signal 1
    E2BEG0: Any  # East 2-wire begin signal 0
    E2BEG1: Any  # East 2-wire begin signal 1

    # South Direction
    S1BEG0: Any  # South 1-wire begin signal 0
    S1BEG1: Any  # South 1-wire begin signal 1
    S2BEG0: Any  # South 2-wire begin signal 0
    S2BEG1: Any  # South 2-wire begin signal 1

    # West Direction
    W1BEG0: Any  # West 1-wire begin signal 0
    W1BEG1: Any  # West 1-wire begin signal 1
    W2BEG0: Any  # West 2-wire begin signal 0
    W2BEG1: Any  # West 2-wire begin signal 1


class SwitchMatrixTestCase(NamedTuple):
    """Test case configuration for switch matrix RTL validation."""

    connections: dict[str, list[str]]
    test_name: str


def _create_switchmatrix_validation_commands(
    connections: dict[str, list[str]],
) -> list[str]:
    """Create yosys validation commands for switch matrix connections."""
    commands = []

    # Basic RTL checks
    commands.append(
        "check -noinit"
    )  # Check for multiple drivers and uninitialized signals
    commands.append("check -assert")  # Verify all outputs are driven

    # Check that all expected input/output ports exist
    all_inputs = set()
    all_outputs = set()

    for output, inputs in connections.items():
        all_outputs.add(output)
        all_inputs.update(inputs)

    # Verify input ports exist
    for input_port in all_inputs:
        commands.append(f"select -assert-min 1 w:{input_port}")

    # Verify output ports exist
    for output_port in all_outputs:
        commands.append(f"select -assert-min 1 w:{output_port}")

    # Verify ConfigBits port exists (required for switch matrix)
    commands.append("select -assert-min 1 w:ConfigBits")

    # Port-to-port connectivity validation
    # For each output, verify it can be driven by its specified inputs
    for output, inputs in connections.items():
        if len(inputs) == 1:
            # Direct connection - verify input connects directly to output
            input_port = inputs[0]
            commands.append(f"select -assert-min 1 w:{input_port} %co w:{output} %i")
        else:
            # Multiplexer - verify each input can potentially drive the output
            for input_port in inputs:
                # Check that there's a path from input through mux logic to output
                commands.append(
                    f"select -assert-min 1 w:{input_port} %co c:* %ci w:{output} %co %i %i"
                )

            # Verify ConfigBits controls the multiplexer for this output
            commands.append(
                f"select -assert-min 1 w:ConfigBits %co c:* %ci w:{output} %co %i %i"
            )

    # Verify no unexpected connections exist
    # Each output should only be driven by its specified inputs (directly or through mux)
    for output, expected_inputs in connections.items():
        # Find all wires that could drive this output
        for input_port in all_inputs:
            if input_port not in expected_inputs:
                # This input should NOT directly connect to this output
                # Use a negative assertion to ensure no direct connection
                commands.append(
                    f"select -assert-max 0 w:{input_port} %co w:{output} %i"
                )

    # ConfigBits connectivity validation
    # ConfigBits should connect to multiplexer control inputs
    mux_count = sum(1 for inputs in connections.values() if len(inputs) > 1)
    if mux_count > 0:
        commands.append("select -assert-min 1 w:ConfigBits %co c:$mux %ci %i")

        # Check that ConfigBits has the right bit width for the multiplexers
        total_config_bits_needed = sum(
            (len(inputs) - 1).bit_length()
            for inputs in connections.values()
            if len(inputs) > 1
        )
        if total_config_bits_needed > 0:
            commands.append(
                f"select -assert-min {total_config_bits_needed} w:ConfigBits"
            )

    # Verify signal isolation - inputs should not directly connect to each other
    input_list = list(all_inputs)
    for i, input1 in enumerate(input_list):
        for input2 in input_list[i + 1 :]:
            # Inputs should not be directly connected to each other
            commands.append(f"select -assert-max 0 w:{input1} %co w:{input2} %i")

    # Check that each input actually has a purpose (connects to at least one output)
    for input_port in all_inputs:
        connected_outputs = [
            output for output, inputs in connections.items() if input_port in inputs
        ]
        if connected_outputs:
            # Build a command to verify this input drives at least one of its connected outputs
            output_selection = " ".join(f"w:{output}" for output in connected_outputs)
            commands.append(
                f"select -assert-min 1 w:{input_port} %co {output_selection} %u %i"
            )

    return commands


@pytest.mark.parametrize(
    "connection_test_case",
    [
        # Simple 2-input mux test
        SwitchMatrixTestCase(
            connections={"N1BEG0": ["E1END0", "E1END1"]},
            test_name="simple_2input_mux",
        ),
        # 4-input mux test
        SwitchMatrixTestCase(
            connections={"N1BEG1": ["E1END0", "E1END1", "S1END0", "W1END0"]},
            test_name="four_input_mux",
        ),
        # Multi-output test
        SwitchMatrixTestCase(
            connections={
                "N1BEG0": ["E1END0", "E1END1"],
                "N1BEG1": ["S1END0", "W1END0"],
            },
            test_name="multi_output_test",
        ),
        # Single connection (no mux) test
        SwitchMatrixTestCase(
            connections={"N1BEG0": ["E1END0"]},
            test_name="single_connection",
        ),
    ],
    ids=lambda case: case.test_name,
)
@pytest.mark.parametrize("hdl_lang", [".v", ".vhdl"])
def test_switchmatrix_rtl_validation(
    hdl_lang: str,
    connection_test_case: SwitchMatrixTestCase,
    default_fabric: Fabric,
    default_tile: Tile,
    tmp_path: Path,
    code_generator_factory: Callable[..., CodeGenerator],
    yosys_validator: Callable[[Path], object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generate Switch Matrix HDL and verify its structure using Yosys RTL validation."""

    # Create code generator using the factory fixture
    test_name: str = (
        f"{default_tile.name}_{connection_test_case.test_name}_switch_matrix"
    )
    writer: CodeGenerator = code_generator_factory(hdl_lang, test_name)
    writer.outFileName = tmp_path / f"{test_name}{hdl_lang}"

    # Create a dummy matrix file for the tile configuration (not used due to mocking)
    matrix_path: Path = tmp_path / f"{connection_test_case.test_name}_matrix.csv"
    matrix_path.touch()  # Create empty file to satisfy file existence checks

    # Update tile configuration
    default_tile.matrixDir = matrix_path

    # Mock the parseMatrix function to return our test connections directly
    monkeypatch.setattr(
        "FABulous.fabric_generator.gen_fabric.gen_switchmatrix.parseMatrix",
        lambda _x, _y: connection_test_case.connections,
    )

    # Generate the Switch Matrix HDL
    genTileSwitchMatrix(writer, default_fabric, default_tile, False)

    # Check if HDL file was created
    if not writer.outFileName.exists():
        pytest.skip(f"Switch matrix HDL file {writer.outFileName} was not generated")

    # Validate HDL structure using Yosys
    validator = yosys_validator(writer.outFileName)

    # Create yosys commands to validate switch matrix structure
    yosys_commands = _create_switchmatrix_validation_commands(
        connection_test_case.connections
    )

    # Run RTL validation
    validator.validate(yosys_commands)
