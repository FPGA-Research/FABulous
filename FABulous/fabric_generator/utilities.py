import os
import re
from typing import Literal, overload
import pathlib

from loguru import logger


def expandListPorts(port, PortList):
    """Expand the .list file entry into a list of tuples.

    Parameters
    ----------
    port : str
        The port entry to expand. If it contains "[", it's split
        into multiple entries based on "|".
    PortList : list
        The list where expanded port entries are appended.

    Raises
    ------
    ValueError
        If the port entry contains "[" without matching "]".
    """
    # a leading '[' tells us that we have to expand the list
    if "[" in port:
        if "]" not in port:
            logger.error("Error in function ExpandListPorts: cannot find closing ]")
            raise ValueError
        # port.find gives us the first occurrence index in a string
        left_index = port.find("[")
        right_index = port.find("]")
        before_left_index = port[0:left_index]
        # right_index is the position of the ']' so we need everything after that
        after_right_index = port[(right_index + 1) :]
        ExpandList = []
        ExpandList = re.split(r"\|", port[left_index + 1 : right_index])
        for entry in ExpandList:
            ExpandListItem = before_left_index + entry + after_right_index
            expandListPorts(ExpandListItem, PortList)

    else:
        # print('DEBUG: else, just:',port)
        PortList.append(port)


# Default parameters (will be overwritten if defined in fabric between 'ParametersBegin' and 'ParametersEnd'
# Parameters = [ 'ConfigBitMode', 'FrameBitsPerRow' ]
CONFIG_BIT_MODE = "FlipFlopChain"
FRAME_BITS_PER_ROW = 32
MAX_FRAMES_PER_COL = 20
PACKAGE = "use work.my_package.all;"
# time in ps - this is needed for simulation as a fabric configuration can result in loops crashing the simulator
GENERATE_DELAY_IN_SWITCH_MATRIX = "100"
# 'custom': using our hard-coded MUX-4 and MUX-16; 'generic': using standard generic RTL code
MULTIPLEXER_STYLE = "custom"
# generate switch matrix select signals (index) which is useful to verify if bitstream matches bitstream
SWITCH_MATRIX_DEBUG_SIGNAL = True
SUPER_TILE_ENABLE = True  # enable SuperTile generation

src_dir = "./"

# TILE field aliases
direction = 0
source_name = 1
X_offset = 2
Y_offset = 3
destination_name = 4
wires = 5

# bitstream mapping aliases
frame_name = 0
frame_index = 1
bits_used_in_frame = 2
used_bits_mask = 3
ConfigBits_ranges = 4

# columns where VHDL file is specified
VHDL_file_position = 1
TileType_position = 1

# BEL prefix field (needed to allow multiple instantiations of the same BEL inside the same tile)
BEL_prefix = 2
# MISC
All_Directions = ["NORTH", "EAST", "SOUTH", "WEST"]
Opposite_Directions = {
    "NORTH": "SOUTH",
    "EAST": "WEST",
    "SOUTH": "NORTH",
    "WEST": "EAST",
}


sDelay = "8"
GNDRE = re.compile(r"GND(\d*)")
VCCRE = re.compile(r"VCC(\d*)")
VDDRE = re.compile(r"VDD(\d*)")
BracketAddingRE = re.compile(r"^(\S+?)(\d+)$")
letters = [
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
    "N",
    "O",
    "P",
    "Q",
    "R",
    "S",
    "T",
    "U",
    "V",
    "W",
]  # For LUT labelling


# Given a fabric array description, return all uniq cell types
def GetCellTypes(list):
    # make the fabric flat
    flat_list = []
    for sublist in list:
        for item in sublist:
            flat_list.append(item)

    output = []
    for item in flat_list:
        if item not in output:
            output.append(item)

    # we use the keyword 'NULL' for padding tiles that we don't return
    if "NULL" in output:
        output.remove("NULL")

    return output


# take a list and remove all items that contain a #    and remove empty lines
def RemoveComments(list):
    output = []

    for line in list:
        templine = []
        marker = False  # we use this marker to remember if we had an '#' element before
        for item in line:
            if item.startswith("#"):
                marker = True
            if not (item.startswith("#") or marker == True):
                # marker = True
                templine.append(item)
                if item == "":
                    templine.remove("")
        if templine != []:
            output.append(templine)
    return output


def GetFabric(list, filter="Fabric"):
    templist = []
    # output = []
    marker = False

    for sublist in list:
        if filter + "End" in sublist:  # was FabricEnd
            marker = False
        if marker == True:
            templist.append(sublist)
        # we place this conditional after the append such that the 'FabricBegin' will be kicked out
        if filter + "Begin" in sublist:  # was FabricBegin
            marker = True
    return RemoveComments(templist)


def GetTileFromFile(list, TileType):
    templist = []
    # output = []
    marker = False

    for sublist in list:
        if "EndTILE" in sublist:
            marker = False
        if ("TILE" in sublist) and (TileType in sublist):
            marker = True
        if marker == True:
            templist.append(sublist)
        # we place this conditional after the append such that the 'FabricBegin' will be kicked out
        # if ('TILE' in sublist) and (type in sublist):
        # if ('TILE' in sublist) and (TileType in sublist):
        # marker = True
    return RemoveComments(templist)


def GetSuperTileFromFile(list):
    templist = []
    tempdict = {}
    superTile_type = ""
    marker = False
    for sublist in list:
        if "SuperTILE" in sublist:
            marker = True
            superTile_type = sublist[1]
            continue
        elif "EndSuperTILE" in sublist:
            marker = False
            tempdict[superTile_type] = RemoveComments(templist)
            templist = []
            continue
        if marker == True:
            templist.append(sublist)
    return tempdict


def PrintTileComponentPort(tile_description, entity, direction, file):
    print("\t-- ", direction, file=file)
    for line in tile_description:
        if line[0] == direction:
            print(
                "\t\t",
                line[source_name],
                "\t: out \tSTD_LOGIC_VECTOR( ",
                end="",
                file=file,
            )
            print(
                (
                    (abs(int(line[X_offset])) + abs(int(line[Y_offset])))
                    * int(line[wires])
                )
                - 1,
                end="",
                file=file,
            )
            print(" downto 0 );", end="", file=file)
            print("\t -- wires: ", line[wires], file=file)
    for line in tile_description:
        if line[0] == direction:
            print(
                "\t\t",
                line[destination_name],
                "\t: in \tSTD_LOGIC_VECTOR( ",
                end="",
                file=file,
            )
            print(
                (
                    (abs(int(line[X_offset])) + abs(int(line[Y_offset])))
                    * int(line[wires])
                )
                - 1,
                end="",
                file=file,
            )
            print(" downto 0 );", end="", file=file)
            print("\t -- wires: ", line[wires], file=file)
    return


def replace(string, substitutions):
    substrings = sorted(substitutions, key=len, reverse=True)
    regex = re.compile("|".join(map(re.escape, substrings)))
    return regex.sub(lambda match: substitutions[match.group(0)], string)


def GetComponentPortsFromFile(
    VHDL_file_name, filter="ALL", port="internal", BEL_Prefix=""
):
    VHDLfile = [line.rstrip("\n") for line in open(f"{src_dir}/{VHDL_file_name}")]

    Inputs = []
    Outputs = []
    ExternalPorts = []
    marker = False
    FoundEntityMarker = False
    DoneMarker = False
    direction = ""
    for line in VHDLfile:
        # the order of the if-statements are important ;
        if re.search("^entity", line, flags=re.IGNORECASE):
            FoundEntityMarker = True

        # detect the direction from comments, like "--NORTH"
        # we need this to filter for a specific direction
        # this implies of course that this information is provided in the VHDL entity
        if re.search("NORTH", line, flags=re.IGNORECASE):
            direction = "NORTH"
        if re.search("EAST", line, flags=re.IGNORECASE):
            direction = "EAST"
        if re.search("SOUTH", line, flags=re.IGNORECASE):
            direction = "SOUTH"
        if re.search("WEST", line, flags=re.IGNORECASE):
            direction = "WEST"

        # all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
        if re.search("-- global", line, flags=re.IGNORECASE):
            FoundEntityMarker = False
            marker = False
            DoneMarker = True

        if (
            (marker == True)
            and (DoneMarker == False)
            and (direction == filter or filter == "ALL")
        ):
            # detect if the port has to be exported as EXTERNAL which is flagged by the comment
            if re.search("EXTERNAL", line):
                External = True
            else:
                External = False
            if re.search("CONFIG_PORT", line):
                Config = True
            else:
                Config = False
            # get rid of everything with and after the ';' that will also remove comments
            # substitutions = {';.*', '', '--.*', '', ',.*', ''}
            # tmp_line=(replace(line, substitutions))
            # tmp_line = (re.sub(';.*', '',(re.sub('--.*', '',line, flags=re.IGNORECASE)), flags=re.IGNORECASE))
            tmp_line = re.sub(
                ";.*",
                "",
                (
                    re.sub(
                        "--.*",
                        "",
                        (re.sub(",.*", "", line, flags=re.IGNORECASE)),
                        flags=re.IGNORECASE,
                    )
                ),
                flags=re.IGNORECASE,
            )
            std_vector = ""
            if re.search("std_logic_vector", tmp_line, flags=re.IGNORECASE):
                std_vector = re.sub(
                    ".*std_logic_vector", "", tmp_line, flags=re.IGNORECASE
                )
            tmp_line = re.sub("STD_LOGIC.*", "", tmp_line, flags=re.IGNORECASE)

            substitutions = {" ": "", "\t": ""}
            tmp_line = replace(tmp_line, substitutions)
            # at this point, we get clean port names, like
            # A0:in
            # A1:in
            # A2:in
            # The following is for internal fabric signal ports (e.g., a CLB/LUT)
            if (port == "internal") and (External == False) and (Config == False):
                if re.search(":in", tmp_line, flags=re.IGNORECASE):
                    Inputs.append(
                        BEL_Prefix
                        + (re.sub(":in.*", "", tmp_line, flags=re.IGNORECASE))
                        + std_vector
                    )
                if re.search(":out", tmp_line, flags=re.IGNORECASE):
                    Outputs.append(
                        BEL_Prefix
                        + (re.sub(":out.*", "", tmp_line, flags=re.IGNORECASE))
                        + std_vector
                    )
            # The following is for ports that have to go all the way up to the top-level entity (e.g., from an I/O cell)
            if (port == "external") and (External == True):
                # .lstrip() removes leading white spaces including ' ', '\t'
                ExternalPorts.append(BEL_Prefix + line.lstrip())

            # frame reconfiguration needs a port for writing in frame data
            if (port == "frame_config") and (Config == True):
                # .lstrip() removes leading white spaces including ' ', '\t'
                ExternalPorts.append(BEL_Prefix + line.lstrip())

        if re.search("port", line, flags=re.IGNORECASE):
            marker = True
    if port == "internal":  # default
        return Inputs, Outputs
    else:
        return ExternalPorts


def GetComponentPortsFromVerilog(
    Verilog_file_name, filter="ALL", port="internal", BEL_Prefix=""
):
    Verilogfile = [line.rstrip("\n") for line in open(Verilog_file_name)]
    Inputs = []
    Outputs = []
    ExternalPorts = []
    marker = False
    FoundEntityMarker = False
    DoneMarker = False
    direction = ""
    for line in Verilogfile:
        # the order of the if-statements are important ;
        if re.search("^module", line, flags=re.IGNORECASE):
            FoundEntityMarker = True

        # detect the direction from comments, like "--NORTH"
        # we need this to filter for a specific direction
        # this implies of course that this information is provided in the VHDL entity
        if re.search("NORTH", line, flags=re.IGNORECASE):
            direction = "NORTH"
        if re.search("EAST", line, flags=re.IGNORECASE):
            direction = "EAST"
        if re.search("SOUTH", line, flags=re.IGNORECASE):
            direction = "SOUTH"
        if re.search("WEST", line, flags=re.IGNORECASE):
            direction = "WEST"

        # all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
        if re.search("// global", line, flags=re.IGNORECASE):
            FoundEntityMarker = False
            marker = False
            DoneMarker = True

        if (
            (marker == True)
            and (DoneMarker == False)
            and (direction == filter or filter == "ALL")
        ):
            # detect if the port has to be exported as EXTERNAL which is flagged by the comment
            if re.search("EXTERNAL", line):
                External = True
            else:
                External = False
            if re.search("CONFIG_PORT", line):
                Config = True
            else:
                Config = False
            # get rid of everything with and after the ';' that will also remove comments
            # substitutions = {';.*', '', '--.*', '', ',.*', ''}
            # tmp_line=(replace(line, substitutions))
            # tmp_line = (re.sub(';.*', '',(re.sub('--.*', '',line, flags=re.IGNORECASE)), flags=re.IGNORECASE))
            tmp_line = re.sub(
                ";.*",
                "",
                (
                    re.sub(
                        "//.*",
                        "",
                        (re.sub(",.*", "", line, flags=re.IGNORECASE)),
                        flags=re.IGNORECASE,
                    )
                ),
                flags=re.IGNORECASE,
            )
            std_vector = ""
            if re.search("input", tmp_line, flags=re.IGNORECASE) or re.search(
                "output", tmp_line, flags=re.IGNORECASE
            ):
                std_vector = re.sub(
                    ".*std_logic_vector", "", tmp_line, flags=re.IGNORECASE
                )
            tmp_line = re.sub("STD_LOGIC.*", "", tmp_line, flags=re.IGNORECASE)

            substitutions = {" ": "", "\t": ""}
            tmp_line = replace(tmp_line, substitutions)
            # at this point, we get clean port names, like
            # A0:in
            # A1:in
            # A2:in
            # The following is for internal fabric signal ports (e.g., a CLB/LUT)
            if (port == "internal") and (External == False) and (Config == False):
                if (
                    re.search(":in", tmp_line, flags=re.IGNORECASE)
                    and "integer" not in tmp_line
                ):
                    Inputs.append(
                        BEL_Prefix
                        + (re.sub(":in.*", "", tmp_line, flags=re.IGNORECASE))
                        + std_vector
                    )
                if re.search(":out", tmp_line, flags=re.IGNORECASE):
                    Outputs.append(
                        BEL_Prefix
                        + (re.sub(":out.*", "", tmp_line, flags=re.IGNORECASE))
                        + std_vector
                    )
            # The following is for ports that have to go all the way up to the top-level entity (e.g., from an I/O cell)
            if (port == "external") and (External == True):
                # .lstrip() removes leading white spaces including ' ', '\t'
                ExternalPorts.append(BEL_Prefix + line.lstrip())

            # frame reconfiguration needs a port for writing in frame data
            if (port == "frame_config") and (Config == True):
                # .lstrip() removes leading white spaces including ' ', '\t'
                ExternalPorts.append(BEL_Prefix + line.lstrip())

        if re.search("port", line, flags=re.IGNORECASE):
            marker = True
    if port == "internal":  # default
        return Inputs, Outputs
    else:
        return ExternalPorts


def GetNoConfigBitsFromFile(VHDL_file_name):
    with open(VHDL_file_name, "r") as f:
        file = f.read()
    result = re.search(
        r"NoConfigBits\s*:\s*integer\s*:=\s*(\w+)", file, flags=re.IGNORECASE
    )
    if result:
        try:
            return int(result.group(1))
        except ValueError:
            return 0


def GetComponentEntityNameFromFile(VHDL_file_name):
    VHDLfile = [line.rstrip("\n") for line in open(f"{src_dir}/{VHDL_file_name}")]
    for line in VHDLfile:
        # the order of the if-statements is important
        if re.search("^entity", line, flags=re.IGNORECASE):
            result = re.sub(
                " ",
                "",
                (
                    re.sub(
                        "entity",
                        "",
                        (re.sub(" is.*", "", line, flags=re.IGNORECASE)),
                        flags=re.IGNORECASE,
                    )
                ),
            )
    return result


def GetComponentEntityNameFromVerilog(Verilog_file_name):
    Verilogfile = [line.rstrip("\n") for line in open(f"{src_dir}/{Verilog_file_name}")]
    for line in Verilogfile:
        # the order of the if-statements is important
        if re.search("^module", line, flags=re.IGNORECASE):
            result = re.sub(
                " ",
                "",
                (
                    re.sub(
                        "module",
                        "",
                        (re.sub(" (.*", "", line, flags=re.IGNORECASE)),
                        flags=re.IGNORECASE,
                    )
                ),
            )
    return result


def GetTileComponentPorts(tile_description, mode="SwitchMatrix"):
    Inputs = []
    Outputs = []
    OpenIndex = ""
    CloseIndex = ""
    if re.search("Indexed", mode, flags=re.IGNORECASE):
        OpenIndex = "("
        CloseIndex = ")"
    for line in tile_description:
        if (
            (line[direction] == "NORTH")
            or (line[direction] == "EAST")
            or (line[direction] == "SOUTH")
            or (line[direction] == "WEST")
        ):
            # range (wires-1 downto 0) as connected to the switch matrix
            if mode in ["SwitchMatrix", "SwitchMatrixIndexed"]:
                ThisRange = int(line[wires])
            if mode in ["AutoSwitchMatrix", "AutoSwitchMatrixIndexed"]:
                if line[source_name] == "NULL" or line[destination_name] == "NULL":
                    # the following line connects all wires to the switch matrix in the case one port is NULL (typically termination)
                    ThisRange = (
                        abs(int(line[X_offset])) + abs(int(line[Y_offset]))
                    ) * int(line[wires])
                else:
                    # the following line connects all bottom wires to the switch matrix in the case begin and end ports are used
                    ThisRange = int(line[wires])
            # range ((wires*distance)-1 downto 0) as connected to the tile top
            if mode in [
                "all",
                "allIndexed",
                "Top",
                "TopIndexed",
                "AutoTop",
                "AutoTopIndexed",
            ]:
                ThisRange = (abs(int(line[X_offset])) + abs(int(line[Y_offset]))) * int(
                    line[wires]
                )
            # the following three lines are needed to get the top line[wires] that are actually the connection from a switch matrix to the routing fabric
            StartIndex = 0
            if mode in ["Top", "TopIndexed"]:
                StartIndex = (
                    (abs(int(line[X_offset])) + abs(int(line[Y_offset]))) - 1
                ) * int(line[wires])
            if mode in ["AutoTop", "AutoTopIndexed"]:
                if line[source_name] == "NULL" or line[destination_name] == "NULL":
                    # in case one port is NULL, then the all the other port wires get connected to the switch matrix.
                    StartIndex = 0
                else:
                    # "normal" case as for the CLBs
                    StartIndex = (
                        (abs(int(line[X_offset])) + abs(int(line[Y_offset]))) - 1
                    ) * int(line[wires])
            for i in range(StartIndex, ThisRange):
                if line[destination_name] != "NULL":
                    Inputs.append(
                        line[destination_name] + OpenIndex + str(i) + CloseIndex
                    )
                if line[source_name] != "NULL":
                    Outputs.append(line[source_name] + OpenIndex + str(i) + CloseIndex)

    return Inputs, Outputs


def GetTileComponentPortsVectors(tile_description, mode):
    Inputs = []
    Outputs = []
    MaxIndex = 0
    for line in tile_description:
        if (
            (line[direction] == "NORTH")
            or (line[direction] == "EAST")
            or (line[direction] == "SOUTH")
            or (line[direction] == "WEST")
        ):
            # range (wires-1 downto 0) as connected to the switch matrix
            if mode in ["SwitchMatrix", "SwitchMatrixIndexed"]:
                MaxIndex = int(line[wires])
            # range ((wires*distance)-1 downto 0) as connected to the tile top
            if mode in ["all", "allIndexed"]:
                MaxIndex = (abs(int(line[X_offset])) + abs(int(line[Y_offset]))) * int(
                    line[wires]
                )
            if line[destination_name] != "NULL":
                Inputs.append(
                    str(line[destination_name] + "(" + str(MaxIndex) + " downto 0)")
                )
            if line[source_name] != "NULL":
                Outputs.append(
                    str(line[source_name] + "(" + str(MaxIndex) + " downto 0)")
                )
    return Inputs, Outputs


def PrintCSV_FileInfo(CSV_FileName):
    CSVFile = [i.strip("\n").split(",") for i in open(CSV_FileName)]
    print("Tile: ", str(CSVFile[0][0]), "\n")

    # print('DEBUG:',CSVFile)

    print("\nInputs: \n")
    CSVFileRows = len(CSVFile)
    # for port in CSVFile[0][1:]:
    line = CSVFile[0]
    for k in range(1, len(line)):
        PortList = []
        PortCount = 0
        for j in range(1, len(CSVFile)):
            if CSVFile[j][k] != "0":
                PortList.append(CSVFile[j][0])
                PortCount += 1
        print(line[k], " connects to ", PortCount, " ports: ", PortList)

    print("\nOutputs: \n")
    for line in CSVFile[1:]:
        # we first count the number of multiplexer inputs
        mux_size = 0
        PortList = []
        # for port in line[1:]:
        # if port != '0':
        for k in range(1, len(line)):
            if line[k] != "0":
                mux_size += 1
                PortList.append(CSVFile[0][k])
        print(line[0], ",", str(mux_size), ", Source port list: ", PortList)
    return


def ExpandListPorts(port, PortList):
    # a leading '[' tells us that we have to expand the list
    if re.search("\[", port):
        if not re.search("\]", port):
            logger.error("Error in function ExpandListPorts: cannot find closing ]")
            raise ValueError
        # port.find gives us the first occurrence index in a string
        left_index = port.find("[")
        right_index = port.find("]")
        before_left_index = port[0:left_index]
        # right_index is the position of the ']' so we need everything after that
        after_right_index = port[(right_index + 1) :]
        ExpandList = []
        ExpandList = re.split("\|", port[left_index + 1 : right_index])
        for entry in ExpandList:
            ExpandListItem = before_left_index + entry + after_right_index
            ExpandListPorts(ExpandListItem, PortList)

    else:
        # print('DEBUG: else, just:',port)
        PortList.append(port)
    return


def takes_list(a_string, a_list):
    print("first debug (a_list):", a_list, "string:", a_string)
    for item in a_list:
        print("hello debug:", item, "string:", a_string)


def GetVerilogDeclarationForFile(VHDL_file_name):
    ConfigPortUsed = 0  # 1 means is used
    VHDLfile = [line.rstrip("\n") for line in open(f"{src_dir}/{VHDL_file_name}")]
    templist = []
    # for item in VHDLfile:
    # print(item)
    for line in VHDLfile:
        # NumberOfConfigBits:0 means no configuration port
        if re.search("NumberOfConfigBits", line, flags=re.IGNORECASE):
            # NumberOfConfigBits appears, so we may have a config port
            ConfigPortUsed = 1
            # but only if the following is not true
            if re.search("NumberOfConfigBits:0", line, flags=re.IGNORECASE):
                ConfigPortUsed = 0
    # print('', file=file)
    return ConfigPortUsed
