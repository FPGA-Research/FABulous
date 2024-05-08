import re
from typing import overload, Literal
import os


def parseMatrix(fileName: str, tileName: str) -> dict[str, list[str]]:
    """
    parse the matrix csv into a dictionary from destination to source

    Args:
        fileName (str): directory of the matrix csv file
        tileName (str): name of the tile need to be parsed

    Raises:
        ValueError: Non matching matrix file content and tile name

    Returns:
        dict[str, list[str]]: dictionary from destination to a list of source
    """

    connectionsDic = {}
    with open(fileName, "r") as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)
        file = file.split("\n")

    if file[0].split(",")[0] != tileName:
        print(fileName)
        print(file[0].split(","))
        print(tileName)
        raise ValueError(
            "Tile name (top left element) in csv file does not match tile name in tile object"
        )

    destList = file[0].split(",")[1:]

    for i in file[1:]:
        i = i.split(",")
        portName, connections = i[0], i[1:]
        if portName == "":
            continue
        indices = [k for k, v in enumerate(connections) if v == "1"]
        connectionsDic[portName] = [destList[j] for j in indices]
    return connectionsDic


@overload
def parseList(
    fileName: str, collect: Literal["pair"] = "pair"
) -> list[tuple[str, str]]:
    pass


@overload
def parseList(
    fileName: str, collect: Literal["source", "sink"]
) -> dict[str, list[str]]:
    pass


def parseList(
    fileName: str, collect: Literal["pair", "source", "sink"] = "pair"
) -> list[tuple[str, str]] | dict[str, list[str]]:
    """
    parse a list file and expand the list file information into a list of tuples.

    Args:
        fileName (str): ""
        collect (Literal[&quot;&quot;, &quot;source&quot;, &quot;sink&quot;], optional): Collect value by source, sink or just as pair. Defaults to "pair".

    Raises:
        ValueError: The file does not exist.
        ValueError: Invalid format in the list file.

    Returns:
        Union[list[tuple[str, str]], dict[str, list[str]]]: Return either a list of connection pair or a dictionary of lists which is collected by the specified option, source or sink.
    """

    if not os.path.exists(fileName):
        raise ValueError(f"The file {fileName} does not exist.")

    resultList = []
    with open(fileName, "r") as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)
    file = file.split("\n")
    for i, line in enumerate(file):
        line = line.replace(" ", "").replace("\t", "").split(",")
        line = [i for i in line if i != ""]
        if not line:
            continue
        if len(line) != 2:
            print(line)
            raise ValueError(f"Invalid list formatting in file: {fileName} at line {i}")
        left, right = line[0], line[1]

        leftList = []
        rightList = []
        _expandListPorts(left, leftList)
        _expandListPorts(right, rightList)
        resultList += list(zip(leftList, rightList))

    result = list(dict.fromkeys(resultList))
    resultDic = {}
    if collect == "source":
        for k, v in result:
            if k not in resultDic:
                resultDic[k] = []
            resultDic[k].append(v)
        return resultDic

    if collect == "sink":
        for k, v in result:
            for i in v:
                if i not in resultDic:
                    resultDic[i] = []
                resultDic[i].append(k)
        return resultDic

    return result


def _expandListPorts(port, PortList):
    """
    expand the .list file entry into list of tuple.
    """
    # a leading '[' tells us that we have to expand the list
    if "[" in port:
        if "]" not in port:
            raise ValueError(
                "\nError in function ExpandListPorts: cannot find closing ]\n"
            )
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
            _expandListPorts(ExpandListItem, PortList)

    else:
        # print('DEBUG: else, just:',port)
        PortList.append(port)
    return


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
GNDRE = re.compile("GND(\d*)")
VCCRE = re.compile("VCC(\d*)")
VDDRE = re.compile("VDD(\d*)")
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
            raise ValueError(
                "\nError in function ExpandListPorts: cannot find closing ]\n"
            )
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


# This class represents individual tiles in the architecture
class TileModelGen:
    tileType = ""
    bels = []
    belsWithIO = (
        []
    )  # Currently the plan is to deprecate bels and replace it with this. However, this would require nextpnr model generation changes, so I won't do that until the VPR foundations are established
    # Format for belsWithIO is [bel name, prefix, inputs, outputs, whether it has a clock input]
    # Format for bels is [bel name, prefix, ports, whether it has a clock input]
    wires = []
    # For storing single wires (to handle cascading and termination)
    atomicWires = []
    pips = []
    belPorts = set()
    matrixFileName = ""
    pipMuxes_MapSourceToSinks = []
    pipMuxes_MapSinkToSources = []
    x = -1  # Init with negative values to ease debugging
    y = -1

    def __init__(self, inType):
        self.tileType = inType

    def genTileLoc(self, separate=False):
        if separate:
            return ("X" + str(self.x), "Y" + str(self.y))
        return "X" + str(self.x) + "Y" + str(self.y)


# This class represents the fabric as a whole
class FabricModelGen:
    tiles = []
    height = 0
    width = 0
    cellTypes = []

    def __init__(self, inHeight, inWidth):
        self.width = inWidth
        self.height = inHeight

    def getTileByCoords(self, x: int, y: int):
        for row in self.tiles:
            for tile in row:
                if tile.x == x and tile.y == y:
                    return tile
        # raise ValueError(f"{x}, {y} is not a valid tile coordinate")

    def getTileByLoc(self, loc: str):
        for row in self.tiles:
            for tile in row:
                if tile.genTileLoc() == loc:
                    return tile
        return None

    def getTileAndWireByWireDest(self, loc: str, dest: str, jumps: bool = True):
        for row in self.tiles:
            for tile in row:
                for wire in tile.wires:
                    if not jumps:
                        if wire["direction"] == "JUMP":
                            continue
                    for i in range(int(wire["wire-count"])):
                        desty = tile.y + int(wire["yoffset"])
                        destx = tile.x + int(wire["xoffset"])
                        desttileLoc = f"X{destx}Y{desty}"
                        if (desttileLoc == loc) and (
                            wire["destination"] + str(i) == dest
                        ):
                            return (tile, wire, i)
        return None


# Method to add square brackets for wire pair generation (to account for different reference styles)
def addBrackets(portIn: str, tile: TileModelGen):
    BracketMatch = BracketAddingRE.match(portIn)
    if BracketMatch and portIn not in tile.belPorts:
        return BracketMatch.group(1) + "[" + BracketMatch.group(2) + "]"
    else:
        return portIn


# This function gets a relevant instance of a tile for a given type - this just saves adding more object attributes
def getTileByType(fabricObject: FabricModelGen, cellType: str):
    for line in fabricObject.tiles:
        for tile in line:
            if tile.tileType == cellType:
                return tile
    return None


# This function parses the contents of a CSV with comments removed to get where potential interconnects are
# The current implementation has two potential outputs: pips is a list of pairings (designed for single PIPs), whereas pipsdict maps each source to all possible sinks (designed with multiplexers in mind)
def findPipList(
    csvFile: list, returnDict: bool = False, mapSourceToSinks: bool = False
):
    sinks = [line[0] for line in csvFile]
    sources = csvFile[0]
    pips = []
    pipsdict = {}
    for y, row in enumerate(csvFile[1::]):
        for x, value in enumerate(row[1::]):
            # Remember that x and y are offset
            if value == "1":
                pips.append([sources[x + 1], sinks[y + 1]])
                if mapSourceToSinks:
                    if sources[x + 1] in pipsdict.keys():
                        pipsdict[sources[x + 1]].append(sinks[y + 1])
                    else:
                        pipsdict[sources[x + 1]] = [sinks[y + 1]]
                else:
                    if sinks[y + 1] in pipsdict.keys():
                        pipsdict[sinks[y + 1]].append(sources[x + 1])
                    else:
                        pipsdict[sinks[y + 1]] = [sources[x + 1]]
    if returnDict:
        return pipsdict
    return pips


# Method to remove a known prefix from a string if it is present at the start - this is provided as str.removeprefix in Python 3.9 but has been implemented for compatibility
def removeStringPrefix(mainStr: str, prefix: str):
    if mainStr[0 : len(prefix)] == prefix:
        return mainStr[len(prefix) :]
    else:
        return mainStr


# Method to find all 'hanging' sources and sinks in a fabric (i.e. ports with connections to pips in only one direction e.g. VCC, GND)
# Returns dict mapping tileLoc to hanging pins
def getFabricSourcesAndSinks(archObject: FabricModelGen, assumeSourceSinkNames=True):
    # First, build a list of all fabric inputs/outputs (bel ports and wires) with the tile address
    allFabricInputs = []
    allFabricOutputs = []
    returnDict = {}

    if not assumeSourceSinkNames:
        for row in archObject.tiles:
            for tile in row:
                tileLoc = tile.genTileLoc()

                for bel in tile.belsWithIO:
                    allFabricInputs.extend(
                        [(tileLoc + "." + cInput) for cInput in bel[2]]
                    )
                    allFabricOutputs.extend(
                        [(tileLoc + "." + cOutput) for cOutput in bel[3]]
                    )

                for wire in tile.wires:
                    # Calculate destination location of the wire at hand
                    desty = tile.y + int(wire["yoffset"])
                    destx = tile.x + int(wire["xoffset"])
                    desttileLoc = f"X{destx}Y{desty}"

                    # For every individual wire
                    for i in range(int(wire["wire-count"])):
                        allFabricInputs.append(tileLoc + "." + wire["source"] + str(i))
                        allFabricOutputs.append(
                            desttileLoc + "." + wire["destination"] + str(i)
                        )

                for wire in tile.atomicWires:
                    # Generate location strings for the source and destination
                    allFabricInputs.append(wire["sourceTile"] + "." + wire["source"])
                    allFabricOutputs.append(
                        wire["destTile"] + "." + wire["destination"]
                    )

    # Now we go through all the pips, and if a source/sink doesn't appear in the list we keep it
    for row in archObject.tiles:
        for tile in row:
            tileLoc = tile.genTileLoc()
            sourceSet = set()
            sinkSet = set()
            for pip in tile.pips:
                if assumeSourceSinkNames:
                    if (
                        GNDRE.match(pip[0])
                        or VCCRE.match(pip[0])
                        or VDDRE.match(pip[0])
                    ):
                        sourceSet.add(pip[0])
                else:
                    if (tileLoc + "." + pip[0]) not in allFabricOutputs:
                        sourceSet.add(pip[0])
                    if (tileLoc + "." + pip[1]) not in allFabricInputs:
                        sinkSet.add(pip[1])
            returnDict[tileLoc] = (sourceSet, sinkSet)

    return returnDict


def genFabricObject(fabric: list, FabricFile):
    # The following iterates through the tile designations on the fabric
    archFabric = FabricModelGen(len(fabric), len(fabric[0]))
    portMap = {}
    wireMap = {}
    # for i, line in enumerate(fabric):
    #     for j, tile in enumerate(line):
    #         tileList = GetTileFromFile(FabricFile, tile)
    #         portList = []
    #         for wire in tileList:
    #             if wire[0] in ["NORTH", "SOUTH", "EAST", "WEST"]:
    #                 if wire[1] != "NULL":
    #                     portList.append(wire[1])
    #                 if wire[4] != "NULL":
    #                     portList.append(wire[4])
    #         portMap["I" + str(i) + "J" + str(j)] = portList

    for i, line in enumerate(fabric):
        row = []
        for j, tile in enumerate(line):
            cTile = TileModelGen(tile)
            wires = []
            belList = []
            belListWithIO = []
            tileList = GetTileFromFile(FabricFile, tile)
            portList = []
            wireTextList = []
            for wire in tileList:
                # Handle tile attributes depending on their label
                if wire[0] == "MATRIX":
                    vhdlLoc = wire[1]
                    # csvLoc = vhdlLoc[:-4:] + "csv"
                    csvLoc = vhdlLoc.replace(".vhdl", ".csv")
                    csvLoc = vhdlLoc.replace(".list", ".csv")
                    csvLoc = vhdlLoc.replace(".v", ".csv")
                    cTile.matrixFileName = csvLoc
                    try:
                        csvFile = RemoveComments(
                            [i.strip("\n").split(",") for i in open(csvLoc)]
                        )
                        cTile.pips = findPipList(csvFile)

                        cTile.pipMuxes_MapSourceToSinks = findPipList(
                            csvFile, returnDict=True, mapSourceToSinks=True
                        )
                        cTile.pipMuxes_MapSinkToSources = findPipList(
                            csvFile, returnDict=True, mapSourceToSinks=False
                        )

                    except:
                        raise Exception("CSV File not found.")

                if wire[0] == "BEL":
                    belHasClockInput = False
                    try:
                        ports = GetComponentPortsFromFile(wire[1])
                        # We also want to check whether the component has a clock input
                        # Get all external (routed to top) ports
                        externalPorts = GetComponentPortsFromFile(
                            wire[1], port="external"
                        )
                        for port in externalPorts:
                            # Get port name
                            PortName = re.sub("\:.*", "", port)
                            substitutions = {" ": "", "\t": ""}  # Strip
                            PortName = replace(PortName, substitutions)
                            if (
                                PortName == "UserCLK"
                            ):  # And if UserCLK is in there then we have a clock input
                                belHasClockInput = True

                    except:
                        raise Exception(f"{wire[1]} file for BEL not found")

                    if len(wire) > 2:
                        prefix = wire[2]
                    else:
                        prefix = ""
                    nports = []
                    inputPorts = []
                    outputPorts = []

                    for port in ports[0]:
                        nports.append(prefix + re.sub(" *\(.*\) *", "", str(port)))
                        # Also add to distinct input/output lists
                        inputPorts.append(prefix + re.sub(" *\(.*\) *", "", str(port)))
                    for port in ports[1]:
                        nports.append(prefix + re.sub(" *\(.*\) *", "", str(port)))
                        outputPorts.append(prefix + re.sub(" *\(.*\) *", "", str(port)))
                    cTile.belPorts.update(nports)

                    belListWithIO.append(
                        [
                            wire[1][0:-5:],
                            prefix,
                            inputPorts,
                            outputPorts,
                            belHasClockInput,
                        ]
                    )
                    belList.append([wire[1][0:-5:], prefix, nports, belHasClockInput])

                elif wire[0] in ["NORTH", "SOUTH", "EAST", "WEST"]:
                    # Wires are added in next pass - this pass generates port lists to be used for wire generation
                    if wire[1] != "NULL":
                        portList.append(wire[1])
                    if wire[4] != "NULL":
                        portList.append(wire[4])
                    wireTextList.append(
                        {
                            "direction": wire[0],
                            "source": wire[1],
                            "xoffset": wire[2],
                            "yoffset": wire[3],
                            "destination": wire[4],
                            "wire-count": wire[5],
                        }
                    )
                # We just treat JUMPs as normal wires - however they're only on one tile so we can add them directly
                elif wire[0] == "JUMP":
                    if "NULL" not in wire:
                        wires.append(
                            {
                                "direction": wire[0],
                                "source": wire[1],
                                "xoffset": wire[2],
                                "yoffset": wire[3],
                                "destination": wire[4],
                                "wire-count": wire[5],
                            }
                        )
            cTile.wires = wires
            cTile.x = j
            # cTile.y = archFabric.height - i -1
            cTile.y = i

            cTile.bels = belList
            cTile.belsWithIO = belListWithIO
            row.append(cTile)
            portMap[cTile] = portList
            wireMap[cTile] = wireTextList
        archFabric.tiles.append(row)

        # Add wires to model

    for row in archFabric.tiles:
        for tile in row:
            wires = []
            wireTextList = wireMap[tile]
            tempAtomicWires = []
            # Wires from tile
            for wire in wireTextList:
                xOffset = int(wire["xoffset"])
                yOffset = int(wire["yoffset"])
                wireCount = int(wire["wire-count"])
                destinationTile = archFabric.getTileByCoords(
                    tile.x + xOffset, tile.y + yOffset
                )
                if (
                    abs(xOffset) <= 1
                    and abs(yOffset) <= 1
                    and not ("NULL" in wire.values())
                ):
                    wires.append(wire)
                    portMap[destinationTile].remove(wire["destination"])
                    portMap[tile].remove(wire["source"])
                # If the wire goes off the fabric then we account for cascading by finding the last tile the wire goes through
                elif not ("NULL" in wire.values()):
                    if xOffset != 0:  # If we're moving in the x axis
                        if xOffset > 1:
                            cTile = archFabric.getTileByCoords(
                                tile.x + 1, tile.y + yOffset
                            )  # destination tile
                            for i in range(wireCount * abs(xOffset)):
                                if i < wireCount:
                                    cascaded_i = i + wireCount * (abs(xOffset) - 1)
                                else:
                                    cascaded_i = i - wireCount
                                    tempAtomicWires.append(
                                        {
                                            "direction": "JUMP",
                                            "source": wire["destination"] + str(i),
                                            "xoffset": "0",
                                            "yoffset": "0",
                                            "destination": wire["source"] + str(i),
                                            "sourceTile": tile.genTileLoc(),
                                            "destTile": tile.genTileLoc(),
                                        }
                                    )
                                tempAtomicWires.append(
                                    {
                                        "direction": wire["direction"],
                                        "source": wire["source"] + str(i),
                                        "xoffset": "1",
                                        "yoffset": wire["yoffset"],
                                        "destination": wire["destination"]
                                        + str(cascaded_i),
                                        "sourceTile": tile.genTileLoc(),
                                        "destTile": cTile.genTileLoc(),
                                    }
                                )  # Add atomic wire names
                            portMap[cTile].remove(wire["destination"])
                            portMap[tile].remove(wire["source"])
                        elif xOffset < -1:
                            cTile = archFabric.getTileByCoords(
                                tile.x - 1, tile.y + yOffset
                            )  # destination tile
                            for i in range(wireCount * abs(xOffset)):
                                if i < wireCount:
                                    cascaded_i = i + wireCount * (abs(xOffset) - 1)
                                else:
                                    cascaded_i = i - wireCount
                                    tempAtomicWires.append(
                                        {
                                            "direction": "JUMP",
                                            "source": wire["destination"] + str(i),
                                            "xoffset": "0",
                                            "yoffset": "0",
                                            "destination": wire["source"] + str(i),
                                            "sourceTile": tile.genTileLoc(),
                                            "destTile": tile.genTileLoc(),
                                        }
                                    )
                                tempAtomicWires.append(
                                    {
                                        "direction": wire["direction"],
                                        "source": wire["source"] + str(i),
                                        "xoffset": "-1",
                                        "yoffset": wire["yoffset"],
                                        "destination": wire["destination"]
                                        + str(cascaded_i),
                                        "sourceTile": tile.genTileLoc(),
                                        "destTile": cTile.genTileLoc(),
                                    }
                                )  # Add atomic wire names
                            portMap[cTile].remove(wire["destination"])
                            portMap[tile].remove(wire["source"])
                    elif yOffset != 0:  # If we're moving in the y axis
                        if yOffset > 1:
                            cTile = archFabric.getTileByCoords(
                                tile.x + xOffset, tile.y + 1
                            )  # destination tile
                            for i in range(wireCount * abs(yOffset)):
                                if i < wireCount:
                                    cascaded_i = i + wireCount * (abs(yOffset) - 1)
                                else:
                                    cascaded_i = i - wireCount
                                    tempAtomicWires.append(
                                        {
                                            "direction": "JUMP",
                                            "source": wire["destination"] + str(i),
                                            "xoffset": "0",
                                            "yoffset": "0",
                                            "destination": wire["source"] + str(i),
                                            "sourceTile": tile.genTileLoc(),
                                            "destTile": tile.genTileLoc(),
                                        }
                                    )
                                tempAtomicWires.append(
                                    {
                                        "direction": wire["direction"],
                                        "source": wire["source"] + str(i),
                                        "xoffset": wire["xoffset"],
                                        "yoffset": "1",
                                        "destination": wire["destination"]
                                        + str(cascaded_i),
                                        "sourceTile": tile.genTileLoc(),
                                        "destTile": cTile.genTileLoc(),
                                    }
                                )  # Add atomic wire names

                            portMap[cTile].remove(wire["destination"])
                            portMap[tile].remove(wire["source"])
                        elif yOffset < -1:
                            cTile = archFabric.getTileByCoords(
                                tile.x + xOffset, tile.y - 1
                            )  # destination tile
                            for i in range(wireCount * abs(yOffset)):
                                if i < wireCount:
                                    cascaded_i = i + wireCount * (abs(yOffset) - 1)
                                else:
                                    cascaded_i = i - wireCount
                                    tempAtomicWires.append(
                                        {
                                            "direction": "JUMP",
                                            "source": wire["destination"] + str(i),
                                            "xoffset": "0",
                                            "yoffset": "0",
                                            "destination": wire["source"] + str(i),
                                            "sourceTile": tile.genTileLoc(),
                                            "destTile": tile.genTileLoc(),
                                        }
                                    )
                                tempAtomicWires.append(
                                    {
                                        "direction": wire["direction"],
                                        "source": wire["source"] + str(i),
                                        "xoffset": wire["xoffset"],
                                        "yoffset": "-1",
                                        "destination": wire["destination"]
                                        + str(cascaded_i),
                                        "sourceTile": tile.genTileLoc(),
                                        "destTile": cTile.genTileLoc(),
                                    }
                                )  # Add atomic wire names

                            portMap[cTile].remove(wire["destination"])
                            portMap[tile].remove(wire["source"])
                elif wire["source"] != "NULL" and wire["destination"] == "NULL":
                    source_wire_name = wire["source"]
                    if source_wire_name == "Co":
                        dest_wire_name = "Ci"
                    elif source_wire_name[1] == "2" and source_wire_name[-1] == "b":
                        dest_wire_name = wire["source"].replace("BEGb", "END")
                    elif source_wire_name[1] == "2" and source_wire_name[-1] != "b":
                        dest_wire_name = wire["source"].replace("BEG", "MID")
                    else:
                        dest_wire_name = wire["source"].replace("BEG", "END")
                    if xOffset != 0:  # If we're moving in the x axis
                        if xOffset > 0:
                            cTile = archFabric.getTileByCoords(
                                tile.x + 1, tile.y + yOffset
                            )  # destination tile
                            for i in range(wireCount * abs(xOffset)):
                                tempAtomicWires.append(
                                    {
                                        "direction": wire["direction"],
                                        "source": wire["source"] + str(i),
                                        "xoffset": "1",
                                        "yoffset": wire["yoffset"],
                                        "destination": dest_wire_name + str(i),
                                        "sourceTile": tile.genTileLoc(),
                                        "destTile": cTile.genTileLoc(),
                                    }
                                )  # Add atomic wire names
                            portMap[cTile].remove(dest_wire_name)
                            portMap[tile].remove(wire["source"])
                        elif xOffset < 0:
                            cTile = archFabric.getTileByCoords(
                                tile.x - 1, tile.y + yOffset
                            )  # destination tile
                            for i in range(wireCount * abs(xOffset)):
                                tempAtomicWires.append(
                                    {
                                        "direction": wire["direction"],
                                        "source": wire["source"] + str(i),
                                        "xoffset": "-1",
                                        "yoffset": wire["yoffset"],
                                        "destination": dest_wire_name + str(i),
                                        "sourceTile": tile.genTileLoc(),
                                        "destTile": cTile.genTileLoc(),
                                    }
                                )  # Add atomic wire names
                            portMap[cTile].remove(dest_wire_name)
                            portMap[tile].remove(wire["source"])
                    elif yOffset != 0:  # If we're moving in the y axis
                        if yOffset > 0:
                            cTile = archFabric.getTileByCoords(
                                tile.x + xOffset, tile.y + 1
                            )  # destination tile
                            for i in range(wireCount * abs(yOffset)):
                                tempAtomicWires.append(
                                    {
                                        "direction": wire["direction"],
                                        "source": wire["source"] + str(i),
                                        "xoffset": wire["xoffset"],
                                        "yoffset": "1",
                                        "destination": dest_wire_name + str(i),
                                        "sourceTile": tile.genTileLoc(),
                                        "destTile": cTile.genTileLoc(),
                                    }
                                )  # Add atomic wire names
                            portMap[cTile].remove(dest_wire_name)
                            portMap[tile].remove(wire["source"])
                        elif yOffset < 0:
                            cTile = archFabric.getTileByCoords(
                                tile.x + xOffset, tile.y - 1
                            )  # destination tile
                            for i in range(wireCount * abs(yOffset)):
                                tempAtomicWires.append(
                                    {
                                        "direction": wire["direction"],
                                        "source": wire["source"] + str(i),
                                        "xoffset": wire["xoffset"],
                                        "yoffset": "-1",
                                        "destination": dest_wire_name + str(i),
                                        "sourceTile": tile.genTileLoc(),
                                        "destTile": cTile.genTileLoc(),
                                    }
                                )  # Add atomic wire names
                            portMap[cTile].remove(dest_wire_name)
                            portMap[tile].remove(wire["source"])

            tile.wires.extend(wires)
            tile.atomicWires = tempAtomicWires

    archFabric.cellTypes = GetCellTypes(fabric)

    return archFabric


def genVerilogTemplate(archObject: FabricModelGen):
    templateStr = "// IMPORTANT NOTE: if using VPR, any instantiated BELs with no outputs MUST be instantiated after IO\n"
    templateStr += "// This is because VPR auto-generates names for primitives with no outputs, and we assume OutPass BELs\n"
    templateStr += "// are the first BELs to be auto-named in our constraints file.\n\n"

    templateStr += "module template ();\n"
    for line in archObject.tiles:
        for tile in line:
            for num, belpair in enumerate(tile.bels):
                bel = belpair[0]
                let = letters[num]
                prefix = belpair[1]
                nports = belpair[2]
                tileLoc = tile.genTileLoc()
                # Add template - this just adds to a file to instantiate all IO as a primitive:
                if bel == "IO_1_bidirectional_frame_config_pass":
                    templateStr += f"wire "
                    for i, port in enumerate(nports):
                        templateStr += f"Tile_{tileLoc}_{port}"
                        if i < len(nports) - 1:
                            templateStr += ", "
                        else:
                            templateStr += ";\n"
                    belName = f"Tile_{tileLoc}_{let}"
                    templateStr += f"(* keep *) IO_1_bidirectional_frame_config_pass {belName} (.O(Tile_{tileLoc}_{prefix}O), .Q(Tile_{tileLoc}_{prefix}Q), .I(Tile_{tileLoc}_{prefix}I));\n\n"
                if bel == "InPass4_frame_config":
                    templateStr += f"wire "
                    for i, port in enumerate(nports):
                        templateStr += f"Tile_{tileLoc}_{port}"
                        if i < len(nports) - 1:
                            templateStr += ", "
                        else:
                            templateStr += ";\n"
                    belName = f"Tile_{tileLoc}_{let}"
                    templateStr += f"(* keep *) InPass4_frame_config {belName} (.O0(Tile_{tileLoc}_{prefix}O0), .O1(Tile_{tileLoc}_{prefix}O1), .O2(Tile_{tileLoc}_{prefix}O2), .O3(Tile_{tileLoc}_{prefix}O3));\n\n"
                if bel == "OutPass4_frame_config":
                    templateStr += f"wire "
                    for i, port in enumerate(nports):
                        templateStr += f"Tile_{tileLoc}_{port}"
                        if i < len(nports) - 1:
                            templateStr += ", "
                        else:
                            templateStr += ";\n"
                    belName = f"Tile_{tileLoc}_{let}"
                    templateStr += f"(* keep *) OutPass4_frame_config {belName} (.I0(Tile_{tileLoc}_{prefix}I0), .I1(Tile_{tileLoc}_{prefix}I1), .I2(Tile_{tileLoc}_{prefix}I2), .I3(Tile_{tileLoc}_{prefix}I3));\n\n"
    templateStr += "endmodule"
    return templateStr


if __name__ == "__main__":
    print(GetComponentPortsFromFile("MULADD.vhdl", port="external"))
