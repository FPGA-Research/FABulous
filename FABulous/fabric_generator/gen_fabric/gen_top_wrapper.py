"""Top-level wrapper generation module.

This module provides functionality to generate the top-level wrapper for FPGA fabrics.
The wrapper includes external I/O connections, configuration interfaces, and optional
BRAM instances. It handles proper port vectorization and grouping for clean top-level
interfaces.
"""

import re
from pathlib import Path

from FABulous.fabric_definition.define import IO
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from FABulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)


def generateTopWrapper(writer: CodeGenerator, fabric: Fabric) -> None:
    """Generate the top wrapper of the fabric.

    This includes features that are not located inside the fabric such as BRAM.
    """

    def split_port(p: str) -> tuple[tuple[int, int], tuple[int, ...], str]:
        """Parse and split a port name into components for sorting and grouping.

        Extracts tile coordinates, port indices, and base name from a port string.
        This enables proper vectorization and ordering of external ports in the
        top-level wrapper.

        Parameters
        ----------
        p : str
            Port name in format "Tile_X{x}Y{y}_{port_name}{indices}"

        Returns
        -------
        tuple[tuple[int, int], tuple[int, ...], str]
            A tuple containing:
            - (y, x): Tile coordinates (y is negated for reverse sorting)
            - indices: Tuple of numeric indices extracted from port name
            - basename: Base port name without coordinates and indices

        Raises
        ------
        ValueError
            If the port name does not match the expected format.

        Examples
        --------
        >>> split_port("Tile_X9Y6_RAM2FAB_D1_I0")
        ((-6, 9), (1, 0), "RAM2FAB_D_I")
        """
        if m := re.match(r"Tile_X(\d+)Y(\d+)_(.*)", p):
            x = int(m.group(1))
            y = int(m.group(2))
            port = m.group(3)
        else:
            raise ValueError(f"Invalid port format: {p}")

        basename = ""
        numbuf = ""
        indices = []
        got_split = False
        for ch in port:
            if ch.isnumeric() and got_split:
                numbuf += ch
            else:
                if ch == "_":
                    # this way we treat the 2 in RAM2FAB as part of the name,
                    # rather than an index
                    got_split = True
                if numbuf != "":
                    indices.append(int(numbuf))
                basename += ch

        if numbuf != "":
            indices.append(int(numbuf))

        # some backwards compat
        basename = basename.removesuffix("_bit")
        # top level IO has A and B parts combined and reverse order
        if len(basename) == 7 and basename[1:] in ("_I_top", "_O_top", "_T_top"):
            assert basename[0] in "ABCDEFGH"
            indices.append(-(ord(basename[0]) - ord("A")))
            basename = basename[2:]

        # Y is in reverse order
        return ((-y, x), tuple(indices), basename)

    # determine external ports so we can group them
    externalPorts = []
    portGroups = dict()
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is not None:
                for bel in tile.bels:
                    for i in bel.externalInput:
                        externalPorts.append((IO.INPUT, f"Tile_X{x}Y{y}_{i}"))
                    for i in bel.externalOutput:
                        externalPorts.append((IO.OUTPUT, f"Tile_X{x}Y{y}_{i}"))
    for iodir, name in externalPorts:
        _yx, _indices, port = split_port(name)
        if port not in portGroups:
            portGroups[port] = (iodir, [])
        portGroups[port][1].append(name)
    # sort port groups according to vectorisation order
    for _name, g in portGroups.items():
        g[1].sort(key=lambda x: split_port(x))

    # header
    numberOfRows = fabric.numberOfRows - 2
    numberOfColumns = fabric.numberOfColumns
    writer.addHeader(f"{fabric.name}_top")
    writer.addParameterStart(indentLevel=1)
    writer.addParameter("include_eFPGA", "integer", 1, indentLevel=2)
    writer.addParameter("NumberOfRows", "integer", numberOfRows, indentLevel=2)
    writer.addParameter(
        "NumberOfCols", "integer", fabric.numberOfColumns, indentLevel=2
    )
    writer.addParameter(
        "FrameBitsPerRow", "integer", fabric.frameBitsPerRow, indentLevel=2
    )
    writer.addParameter(
        "MaxFramesPerCol", "integer", fabric.maxFramesPerCol, indentLevel=2
    )
    writer.addParameter("desync_flag", "integer", fabric.desync_flag, indentLevel=2)
    writer.addParameter(
        "FrameSelectWidth", "integer", fabric.frameSelectWidth, indentLevel=2
    )
    writer.addParameter(
        "RowSelectWidth", "integer", fabric.rowSelectWidth, indentLevel=2
    )
    writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)

    writer.addComment("External IO port", onNewLine=True, indentLevel=2)
    for name, group in sorted(portGroups.items(), key=lambda x: x[0]):
        if fabric.numberOfBRAMs > 0 and ("RAM2FAB" in name or "FAB2RAM" in name):
            continue
        writer.addPortVector(name, group[0], len(group[1]) - 1, indentLevel=2)
    writer.addComment("Config related ports", onNewLine=True, indentLevel=2)
    writer.addPortScalar("CLK", IO.INPUT, indentLevel=2)
    writer.addPortScalar("resetn", IO.INPUT, indentLevel=2)
    writer.addPortScalar("SelfWriteStrobe", IO.INPUT, indentLevel=2)
    writer.addPortVector(
        "SelfWriteData", IO.INPUT, fabric.frameBitsPerRow - 1, indentLevel=2
    )
    writer.addPortScalar("Rx", IO.INPUT, indentLevel=2)
    writer.addPortScalar("ComActive", IO.OUTPUT, indentLevel=2)
    writer.addPortScalar("ReceiveLED", IO.OUTPUT, indentLevel=2)
    writer.addPortScalar("s_clk", IO.INPUT, indentLevel=2)
    writer.addPortScalar("s_data", IO.INPUT, indentLevel=2)
    writer.addPortEnd()
    writer.addHeaderEnd(f"{fabric.name}_top")
    writer.addDesignDescriptionStart(f"{fabric.name}_top")

    # all the wires/connection with in the design
    if "RAM2FAB_D_I" in portGroups and fabric.numberOfBRAMs > 0:
        writer.addComment("BlockRAM ports", onNewLine=True)
        writer.addNewLine()
        writer.addConnectionVector("RAM2FAB_D_I", f"{numberOfRows * 4 * 4}-1")
        writer.addConnectionVector("FAB2RAM_D_O", f"{numberOfRows * 4 * 4}-1")
        writer.addConnectionVector("FAB2RAM_A_O", f"{numberOfRows * 4 * 2}-1")
        writer.addConnectionVector("FAB2RAM_C_O", f"{numberOfRows * 4}-1")

    writer.addNewLine()
    writer.addComment("Signal declarations", onNewLine=True)
    writer.addConnectionVector("FrameRegister", "(NumberOfRows*FrameBitsPerRow)-1")
    writer.addConnectionVector("FrameSelect", "(MaxFramesPerCol*NumberOfCols)-1")
    writer.addConnectionVector("FrameData", "(FrameBitsPerRow*(NumberOfRows+2))-1")
    writer.addConnectionVector("FrameAddressRegister", "FrameBitsPerRow-1")
    writer.addConnectionScalar("LongFrameStrobe")
    writer.addConnectionVector("LocalWriteData", 31)
    writer.addConnectionScalar("LocalWriteStrobe")
    writer.addConnectionVector("RowSelect", "RowSelectWidth-1")

    if isinstance(writer, VHDLCodeGenerator):
        basePath = Path(writer.outFileName).parent
        if not (basePath / "Frame_Data_Reg.vhdl").exists():
            raise FileExistsError(
                "Frame_Data_Reg.vhdl not found in the 'Fabric' directory."
            )
        if not (basePath / "Frame_Select.vhdl").exists():
            raise FileExistsError(
                "Frame_Select.vhdl not found in the 'Fabric' directory."
            )
        if not (basePath / "eFPGA_Config.vhdl").exists():
            raise FileExistsError("Config.vhdl not found in the 'Fabric' directory.")
        if not (basePath / "eFPGA.vhdl").exists():
            raise FileExistsError(
                "eFPGA.vhdl not found in the 'Fabric' directory, "
                "need to generate the eFPGA first."
            )
        if not (basePath / "BlockRAM_1KB.vhdl").exists():
            raise FileExistsError(
                "BlockRAM_1KB.vhdl not found in the 'Fabric' directory."
            )
        writer.addComponentDeclarationForFile(f"{basePath}/Frame_Data_Reg.vhdl")
        writer.addComponentDeclarationForFile(f"{basePath}/Frame_Select.vhdl")
        writer.addComponentDeclarationForFile(f"{basePath}/eFPGA_Config.vhdl")
        writer.addComponentDeclarationForFile(f"{basePath}/eFPGA.vhdl")
        writer.addComponentDeclarationForFile(f"{basePath}/BlockRAM_1KB.vhdl")

    writer.addLogicStart()

    if isinstance(writer, VerilogCodeGenerator):
        writer.addPreprocIfNotDef("EMULATION")

    # the config module
    writer.addNewLine()
    writer.addInstantiation(
        compName="eFPGA_Config",
        compInsName="eFPGA_Config_inst",
        portsPairs=[
            ("CLK", "CLK"),
            ("resetn", "resetn"),
            ("Rx", "Rx"),
            ("ComActive", "ComActive"),
            ("ReceiveLED", "ReceiveLED"),
            ("s_clk", "s_clk"),
            ("s_data", "s_data"),
            ("SelfWriteData", "SelfWriteData"),
            ("SelfWriteStrobe", "SelfWriteStrobe"),
            ("ConfigWriteData", "LocalWriteData"),
            ("ConfigWriteStrobe", "LocalWriteStrobe"),
            ("FrameAddressRegister", "FrameAddressRegister"),
            ("LongFrameStrobe", "LongFrameStrobe"),
            ("RowSelect", "RowSelect"),
        ],
        paramPairs=[
            ("RowSelectWidth", "RowSelectWidth"),
            ("NumberOfRows", "NumberOfRows"),
            ("desync_flag", "desync_flag"),
            ("FrameBitsPerRow", "FrameBitsPerRow"),
        ],
    )
    writer.addNewLine()

    # the frame data reg module
    for row in range(numberOfRows):
        writer.addInstantiation(
            compName="Frame_Data_Reg",
            compInsName=f"inst_Frame_Data_Reg_{row}",
            portsPairs=[
                ("FrameData_I", "LocalWriteData"),
                (
                    "FrameData_O",
                    f"FrameRegister[{row}*FrameBitsPerRow+FrameBitsPerRow-1:{row}*FrameBitsPerRow]",
                ),
                ("RowSelect", "RowSelect"),
                ("CLK", "CLK"),
            ],
            paramPairs=[
                ("FrameBitsPerRow", "FrameBitsPerRow"),
                ("RowSelectWidth", "RowSelectWidth"),
                ("Row", str(row + 1)),
            ],
        )
    writer.addNewLine()

    # the frame select module
    for col in range(numberOfColumns):
        writer.addInstantiation(
            compName="Frame_Select",
            compInsName=f"inst_Frame_Select_{col}",
            portsPairs=[
                ("FrameStrobe_I", "FrameAddressRegister[MaxFramesPerCol-1:0]"),
                (
                    "FrameStrobe_O",
                    f"FrameSelect[{col}*MaxFramesPerCol+MaxFramesPerCol-1:{col}*MaxFramesPerCol]",
                ),
                (
                    "FrameSelect",
                    "FrameAddressRegister[FrameBitsPerRow-1:FrameBitsPerRow-FrameSelectWidth]",
                ),
                ("FrameStrobe", "LongFrameStrobe"),
            ],
            paramPairs=[
                ("MaxFramesPerCol", "MaxFramesPerCol"),
                ("FrameSelectWidth", "FrameSelectWidth"),
                ("Col", str(col)),
            ],
        )
    writer.addNewLine()

    if isinstance(writer, VerilogCodeGenerator):
        writer.addPreprocEndif()

    # the fabric module
    portList = []
    signal = []

    # external ports (IO, config access, BRAM, etc)
    for name, group in sorted(portGroups.items(), key=lambda x: x[0]):
        for i, sig in enumerate(group[1]):
            portList.append(sig)
            signal.append(f"{name}[{i}]")

    portList.append("UserCLK")
    signal.append("CLK")

    portList.append("FrameData")
    signal.append("FrameData")

    portList.append("FrameStrobe")
    signal.append("FrameSelect")

    assert len(portList) == len(signal)
    writer.addInstantiation(
        compName=fabric.name,
        compInsName=f"{fabric.name}_inst",
        portsPairs=list(zip(portList, signal, strict=False)),
    )

    writer.addNewLine()

    # the BRAM module
    if "RAM2FAB_D_I" in portGroups and fabric.numberOfBRAMs > 0:
        data_cap = int((numberOfRows * 4 * 4) / (fabric.numberOfBRAMs - 1))
        addr_cap = int((numberOfRows * 4 * 2) / (fabric.numberOfBRAMs - 1))
        config_cap = int((numberOfRows * 4) / (fabric.numberOfBRAMs - 1))
        for i in range(fabric.numberOfBRAMs - 1):
            portsPairs = [
                ("clk", "CLK"),
                ("rd_addr", f"FAB2RAM_A_O[{addr_cap * i + 8 - 1}:{addr_cap * i}]"),
                ("rd_data", f"RAM2FAB_D_I[{data_cap * i + 32 - 1}:{data_cap * i}]"),
                (
                    "wr_addr",
                    f"FAB2RAM_A_O[{addr_cap * i + 16 - 1}:{addr_cap * i + 8}]",
                ),
                ("wr_data", f"FAB2RAM_D_O[{data_cap * i + 32 - 1}:{data_cap * i}]"),
                ("C0", f"FAB2RAM_C_O[{config_cap * i}]"),
                ("C1", f"FAB2RAM_C_O[{config_cap * i + 1}]"),
                ("C2", f"FAB2RAM_C_O[{config_cap * i + 2}]"),
                ("C3", f"FAB2RAM_C_O[{config_cap * i + 3}]"),
                ("C4", f"FAB2RAM_C_O[{config_cap * i + 4}]"),
                ("C5", f"FAB2RAM_C_O[{config_cap * i + 5}]"),
            ]
            writer.addInstantiation(
                compName="BlockRAM_1KB",
                compInsName=f"Inst_BlockRAM_{i}",
                portsPairs=portsPairs,
            )
    if isinstance(writer, VHDLCodeGenerator):
        writer.addAssignScalar(
            "FrameData", ['X"12345678"', "FrameRegister", 'X"12345678"']
        )
    else:
        writer.addAssignScalar(
            "FrameData", ["32'h12345678", "FrameRegister", "32'h12345678"]
        )
    writer.addDesignDescriptionEnd()
    writer.writeToFile()
