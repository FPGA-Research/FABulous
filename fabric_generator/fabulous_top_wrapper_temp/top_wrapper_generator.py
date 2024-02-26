import re
from array import *
import fileinput
import sys, getopt
import csv


def split_port(p):
    # split a port according to how we want to sort ports:
    # ((y, x), (indices...), basename)
    # Tile_X9Y6_RAM2FAB_D1_I0 --> ((6, 9), (1, 0), "RAM2FAB_D_I")
    m = re.match(r"Tile_X(\d+)Y(\d+)_(.*)", p)
    x = int(m.group(1))
    y = int(m.group(2))
    port = m.group(3)

    basename = ""
    numbuf = ""
    indices = []
    for ch in port:
        if ch.isnumeric():
            numbuf += ch
        else:
            if numbuf != "":
                indices.append(int(numbuf))
            basename += ch

    if numbuf != "":
        indices.append(int(numbuf))

    # some backwards compat
    if basename.endswith("_bit"):
        # _bit is part of the indexing rather than the name
        basename = basename[:-4]
    # top level IO has A and B parts combined
    if len(basename) == 7 and basename[1:] in ("_I_top", "_O_top", "_T_top"):
        assert basename[0] in "ABCDEFGH"
        basename = basename[2:]
        indices.append(ord(basename[0]) - ord("A"))

    # Y is in reverse order
    return ((-y, x), tuple(indices), basename)


def main(argv):
    NumberOfRows = 16
    NumberOfCols = 19
    FrameBitsPerRow = 32
    MaxFramesPerCol = 20
    desync_flag = 20
    FrameSelectWidth = 5
    RowSelectWidth = 5
    NumberOfBRAMs = 4

    fabric = None

    try:
        opts, args = getopt.getopt(
            argv,
            "hr:c:b:f:d:t:",
            [
                "NumberOfRows=",
                "NumberOfCols=",
                "FrameBitsPerRow=",
                "MaxFramesPerCol=",
                "desync_flag=",
                "fabric=",
            ],
        )
    except getopt.GetoptError:
        print(
            "top_wrapper_generator.py -r <NumberOfRows> -c <NumberOfCols> -b <FrameBitsPerRow> -f <MaxFramesPerCol> -d <desync_flag> -t <fabric>"
        )
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-h":
            print(
                "top_wrapper_generator.py -r <NumberOfRows> -c <NumberOfCols> -b <FrameBitsPerRow> -f <MaxFramesPerCol> -d <desync_flag> -t <fabric>"
            )
            sys.exit()
        elif opt in ("-r", "--NumberOfRows"):
            NumberOfRows = int(arg)
        elif opt in ("-c", "--NumberOfCols"):
            NumberOfCols = int(arg) + 2
        elif opt in ("-b", "--FrameBitsPerRow"):
            FrameBitsPerRow = int(arg)
        elif opt in ("-f", "--MaxFramesPerCol"):
            MaxFramesPerCol = int(arg)
        elif opt in ("-d", "--desync_flag"):
            desync_flag = int(arg)
        elif opt in ("-t", "--fabric"):
            fabric = arg

    print("NumberOfRows     :", NumberOfRows)
    print("NumberOfCols     :", NumberOfCols - 2)
    print("FrameBitsPerRow  :", FrameBitsPerRow)
    print("MaxFramesPerCol  :", MaxFramesPerCol)
    print("desync_flag      :", desync_flag)
    print("FrameSelectWidth :", FrameSelectWidth)
    print("RowSelectWidth   :", RowSelectWidth)
    print("")

    wrapper_top_str = ""
    config_str = ""
    configfsm_str = ""
    data_reg_modules = ""
    strobe_reg_modules = ""
    testbench_str = ""
    # data_reg_module_temp = ""

    if fabric is None:
        print("Path to generated fabric.v must be specified with -t fabric.v")
        sys.exit(1)

    # Determine the set of external ports
    port_groups = dict()
    with open(fabric, "r") as file:
        for line in file:
            if m := re.match(
                r"(input|output)\s+(Tile_X\d+Y\d+_[A-Z0-9a-z_]+);\s*//EXTERNAL",
                line.strip(),
            ):
                yx, indices, port = split_port(m.group(2))
                if port not in port_groups:
                    port_groups[port] = (m.group(1), [])
                port_groups[port][1].append(m.group(2))
    # sort port groups according to vectorisation order
    for name, g in port_groups.items():
        g[1].sort(key=lambda x: split_port(x))

    try:
        with open("fabulous_top_wrapper_temp/eFPGA_top_template.v", "r") as file:
            wrapper_top_str = file.read()
    except IOError:
        print("eFPGA_top_template.v not accessible")
        sys.exit(1)

    try:
        with open("fabulous_top_wrapper_temp/Config_template.v", "r") as file:
            config_str = file.read()
    except IOError:
        print("Config_template.v not accessible")
        sys.exit(1)

    try:
        with open("fabulous_top_wrapper_temp/ConfigFSM_template.v", "r") as file:
            configfsm_str = file.read()
    except IOError:
        print("ConfigFSM_template.v not accessible")
        sys.exit(1)

    wrapper_top_str = wrapper_top_str.replace("${NumberOfRows}", str(NumberOfRows))
    wrapper_top_str = wrapper_top_str.replace("${NumberOfCols}", str(NumberOfCols))

    # extra IO for module header
    uio_list = ""
    for name in sorted(port_groups.keys()):
        uio_list += f"{name}, "
    wrapper_top_str = wrapper_top_str.replace("${uio_list}", uio_list)

    # extra IO wires
    uio_wires = ""
    for name, group in sorted(port_groups.items(), key=lambda x: x[0]):
        uio_wires += f"\t{group[0]} wire [{len(group[1])-1}:0] {name};\n"
    wrapper_top_str = wrapper_top_str.replace("${uio_wires}", uio_wires)

    # config_str = config_str.replace("parameter NumberOfRows = 16", "parameter NumberOfRows = "+str(NumberOfRows))
    config_str = config_str.replace(
        "parameter RowSelectWidth = 5",
        "parameter RowSelectWidth = " + str(RowSelectWidth),
    )
    config_str = config_str.replace(
        "parameter FrameBitsPerRow = 32",
        "parameter FrameBitsPerRow = " + str(FrameBitsPerRow),
    )
    # config_str = config_str.replace("parameter desync_flag = 20", "parameter desync_flag = "+str(desync_flag))

    configfsm_str = configfsm_str.replace(
        "parameter NumberOfRows = 16", "parameter NumberOfRows = " + str(NumberOfRows)
    )
    configfsm_str = configfsm_str.replace(
        "parameter RowSelectWidth = 5",
        "parameter RowSelectWidth = " + str(RowSelectWidth),
    )
    configfsm_str = configfsm_str.replace(
        "parameter FrameBitsPerRow = 32",
        "parameter FrameBitsPerRow = " + str(FrameBitsPerRow),
    )
    configfsm_str = configfsm_str.replace(
        "parameter desync_flag = 20", "parameter desync_flag = " + str(desync_flag)
    )

    for row in range(NumberOfRows):
        data_reg_module_temp = ""

        data_reg_name = "Frame_Data_Reg_" + str(row)
        wrapper_top_str += "\t" + data_reg_name + " Inst_" + data_reg_name + " (\n"
        wrapper_top_str += "\t.FrameData_I(LocalWriteData),\n"
        wrapper_top_str += (
            "\t.FrameData_O(FrameRegister["
            + str(row)
            + "*FrameBitsPerRow+:FrameBitsPerRow]),\n"
        )
        wrapper_top_str += "\t.RowSelect(RowSelect),\n"
        wrapper_top_str += "\t.CLK(CLK)\n"
        wrapper_top_str += "\t);\n\n"
        # data_reg_modules += 'module '+data_reg_name+' (FrameData_I, FrameData_O, RowSelect, CLK);'
        try:
            with open(
                "fabulous_top_wrapper_temp/Frame_Data_Reg_template.v", "r"
            ) as file:
                data_reg_module_temp = file.read()
        except IOError:
            print("Frame_Data_Reg_template.v not accessible")
            break
        data_reg_module_temp = data_reg_module_temp.replace(
            "Frame_Data_Reg", data_reg_name
        )
        data_reg_module_temp = data_reg_module_temp.replace(
            "parameter FrameBitsPerRow = 32",
            "parameter FrameBitsPerRow = " + str(FrameBitsPerRow),
        )
        data_reg_module_temp = data_reg_module_temp.replace(
            "parameter RowSelectWidth = 5",
            "parameter RowSelectWidth = " + str(RowSelectWidth),
        )
        data_reg_module_temp = data_reg_module_temp.replace(
            "parameter Row = 1", "parameter Row = " + str(row + 1)
        )
        data_reg_modules += data_reg_module_temp + "\n\n"
        # with open("verilog_output/"+data_reg_name+".v", 'w') as file:
        #    file.write(data_reg_module_temp)

    for col in range(NumberOfCols):
        strobe_reg_module_temp = ""

        strobe_reg_name = "Frame_Select_" + str(col)
        wrapper_top_str += "\t" + strobe_reg_name + " Inst_" + strobe_reg_name + " (\n"
        wrapper_top_str += (
            "\t.FrameStrobe_I(FrameAddressRegister[MaxFramesPerCol-1:0]),\n"
        )
        wrapper_top_str += (
            "\t.FrameStrobe_O(FrameSelect["
            + str(col)
            + "*MaxFramesPerCol +: MaxFramesPerCol]),\n"
        )
        wrapper_top_str += "\t.FrameSelect(FrameAddressRegister[FrameBitsPerRow-1:FrameBitsPerRow-(FrameSelectWidth)]),\n"
        wrapper_top_str += "\t.FrameStrobe(LongFrameStrobe)\n"
        wrapper_top_str += "\t);\n\n"
        try:
            with open("fabulous_top_wrapper_temp/Frame_Select_template.v", "r") as file:
                strobe_reg_module_temp = file.read()
        except IOError:
            print("Frame_Select_template.v not accessible")
            break
        strobe_reg_module_temp = strobe_reg_module_temp.replace(
            "Frame_Select", strobe_reg_name
        )
        strobe_reg_module_temp = strobe_reg_module_temp.replace(
            "parameter MaxFramesPerCol = 20",
            "parameter MaxFramesPerCol = " + str(MaxFramesPerCol),
        )
        strobe_reg_module_temp = strobe_reg_module_temp.replace(
            "parameter FrameSelectWidth = 5",
            "parameter FrameSelectWidth = " + str(FrameSelectWidth),
        )
        strobe_reg_module_temp = strobe_reg_module_temp.replace(
            "parameter Col = 18", "parameter Col = " + str(col)
        )
        strobe_reg_modules += strobe_reg_module_temp + "\n\n"
        # with open("verilog_output/"+strobe_reg_name+".v", 'w') as file:
        #    file.write(strobe_reg_module_temp)

    # wrapper_top_str+='\twire ['+str(NumberOfRows-1)+':0] dump;\n\n'
    wrapper_top_str += "\teFPGA Inst_eFPGA(\n"

    # external IO connectivity
    for name, group in sorted(port_groups.items(), key=lambda x: x[0]):
        for i, sig in enumerate(group[1]):
            wrapper_top_str += f"\t.{sig}({name}[{i}]),\n"

    wrapper_top_str += "\t//declarations\n"
    wrapper_top_str += "\t.UserCLK(CLK),\n"
    wrapper_top_str += "\t.FrameData(FrameData),\n"
    wrapper_top_str += "\t.FrameStrobe(FrameSelect)\n"
    wrapper_top_str += "\t);\n\n"

    wrapper_top_str += (
        "\tassign FrameData = {32'h12345678,FrameRegister,32'h12345678};\n\n"
    )
    wrapper_top_str += "endmodule\n\n"

    if wrapper_top_str:
        with open("eFPGA_top.v", "w") as file:
            file.write(wrapper_top_str)

    if data_reg_modules:
        with open("Frame_Data_Reg_Pack.v", "w") as file:
            file.write(data_reg_modules)

    if strobe_reg_modules:
        with open("Frame_Select_Pack.v", "w") as file:
            file.write(strobe_reg_modules)

    if config_str:
        with open("Config.v", "w") as file:
            file.write(config_str)

    if configfsm_str:
        with open("ConfigFSM.v", "w") as file:
            file.write(configfsm_str)

    # if testbench_str:
    #    with open("tb_bitbang.vhd", 'w') as file:
    #        file.write(testbench_str)

    print("Finish")


if __name__ == "__main__":
    main(sys.argv[1:])


# argv = "/home/ise/shared_folder/diffeq1/LC_on/netgen/synthesis/diffeq_paj_convert_synthesis.v"


# if words[i+1] == "critical":
# number1.append(words[i+3])
# elif x == "Total":
# if words[i+1] == "used":
# number2.append(words[i+5])
# print(number1)
# print(number2)
