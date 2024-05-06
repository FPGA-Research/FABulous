import re
from array import *
import fileinput
import sys
import getopt
import csv
import os
import argparse

FABulous_root = os.getenv("FABulous_root")

if FABulous_root is None:
    print("FABulous_root is not set!")
    print("Set FABulous_root with the following command:")
    print("export FABulous_root=<path to FABulous root>")
    sys.exit(1)

NumberOfRows = 16
NumberOfCols = 19
FrameBitsPerRow = 32
MaxFramesPerCol = 20
desync_flag = 20
FrameSelectWidth = 5
RowSelectWidth = 5
NumberOfBRAMs = 4
output_dir = "."


def main():
    NumberOfBRAMs = int(NumberOfRows / 2)

    print("NumberOfRows     :", NumberOfRows)
    print("NumberOfCols     :", NumberOfCols - 2)
    print("FrameBitsPerRow  :", FrameBitsPerRow)
    print("MaxFramesPerCol  :", MaxFramesPerCol)
    print("desync_flag      :", desync_flag)
    print("FrameSelectWidth :", FrameSelectWidth)
    print("RowSelectWidth   :", RowSelectWidth)
    print("NumberOfBRAMs   :", NumberOfBRAMs)
    print("")

    wrapper_top_str = ""
    config_str = ""
    configfsm_str = ""
    data_reg_modules = ""
    strobe_reg_modules = ""
    testbench_str = ""
    # data_reg_module_temp = ""

    try:
        with open(
            f"{FABulous_root}/fabric_generator/fabulous_top_wrapper_temp/eFPGA_v3_top_sky130_with_BRAM_template.vhdl",
            "r",
        ) as file:
            wrapper_top_str = file.read()
    except IOError:
        print("eFPGA_v3_top_sky130_with_BRAM_template.v not accessible")
        exit(-1)

    try:
        with open(
            f"{FABulous_root}/fabric_generator/fabulous_top_wrapper_temp/Config_template.vhdl",
            "r",
        ) as file:
            config_str = file.read()
    except IOError:
        print("Config_template.v not accessible")
        exit(-1)

    try:
        with open(
            f"{FABulous_root}/fabric_generator/fabulous_top_wrapper_temp/ConfigFSM_template.vhdl",
            "r",
        ) as file:
            configfsm_str = file.read()
    except IOError:
        print("ConfigFSM_template.v not accessible")
        exit(-1)

    try:
        with open(
            f"{FABulous_root}/fabric_generator/fabulous_top_wrapper_temp/tb_bitbang_template.vhd",
            "r",
        ) as file:
            testbench_str = file.read()
    except IOError:
        print("tb_bitbang_template.vhd not accessible")
        exit(-1)

    wrapper_top_str = wrapper_top_str.replace(
        "FrameBitsPerRow : integer := 32;",
        f"FrameBitsPerRow : integer := {FrameBitsPerRow};",
    )
    wrapper_top_str = wrapper_top_str.replace(
        "FrameSelectWidth : integer := 5;",
        f"FrameSelectWidth : integer := {FrameSelectWidth};",
    )
    wrapper_top_str = wrapper_top_str.replace(
        "MaxFramesPerCol : integer := 20;",
        f"MaxFramesPerCol : integer := {MaxFramesPerCol};",
    )
    wrapper_top_str = wrapper_top_str.replace(
        "NumberOfCols : integer := 19;", f"NumberOfCols : integer := {NumberOfCols};"
    )
    wrapper_top_str = wrapper_top_str.replace(
        "NumberOfRows : integer := 16;", f"NumberOfRows : integer := {NumberOfRows};"
    )
    wrapper_top_str = wrapper_top_str.replace(
        "RowSelectWidth : integer := 5;",
        f"RowSelectWidth : integer := {RowSelectWidth};",
    )
    wrapper_top_str = wrapper_top_str.replace(
        "desync_flag : integer := 20;", f"desync_flag : integer := {desync_flag};"
    )

    # wrapper_top_str = wrapper_top_str.replace(
    #     "I_top : out unsigned(31 downto 0)", f"I_top : out unsigned({NumberOfRows*2}-1 downto 0)")
    # wrapper_top_str = wrapper_top_str.replace(
    #     "T_top : out unsigned(31 downto 0)", f"T_top : out unsigned({NumberOfRows*2}-1 downto 0)")
    # wrapper_top_str = wrapper_top_str.replace(
    #     "O_top : in unsigned(31 downto 0)", f"O_top : in unsigned({NumberOfRows*2}-1 downto 0)")

    # wrapper_top_str = wrapper_top_str.replace(
    #     "A_config_C : out unsigned(63 downto 0)", f"A_config_C : out unsigned({NumberOfRows*4}-1 downto 0)")
    # wrapper_top_str = wrapper_top_str.replace(
    #     "B_config_C : out unsigned(63 downto 0)", f"B_config_C : out unsigned({NumberOfRows*4}-1 downto 0)")

    # wrapper_top_str = wrapper_top_str.replace(
    #     "RAM2FAB_D : out unsigned(63 downto 0)", f"RAM2FAB_D : out unsigned({NumberOfRows*4*4}-1 downto 0)")
    # wrapper_top_str = wrapper_top_str.replace(
    #     "signal RAM2FAB_Readable : unsigned(63 downto 0); -- Needed to connect outputs", f"signal RAM2FAB_Readable : unsigned({NumberOfRows*4*4}-1 downto 0); -- Needed to connect outputs")
    # wrapper_top_str = wrapper_top_str.replace(
    #     "FAB2RAM_D : out unsigned(63 downto 0)", f"FAB2RAM_D : out unsigned({NumberOfRows*4*4}-1 downto 0)")
    # wrapper_top_str = wrapper_top_str.replace(
    #     "FAB2RAM_A : out unsigned(63 downto 0)", f"FAB2RAM_A : out unsigned({NumberOfRows*4*2}-1 downto 0)")
    # wrapper_top_str = wrapper_top_str.replace(
    #     "FAB2RAM_C : out unsigned(63 downto 0)", f"FAB2RAM_C : out unsigned({NumberOfRows*4}-1 downto 0)")
    # wrapper_top_str = wrapper_top_str.replace(
    #     "Config_accessC : out unsigned(63 downto 0)", f"Config_accessC : out unsigned({NumberOfRows*4}-1 downto 0)")

    wrapper_top_str = wrapper_top_str.replace(
        "localparam NumberOfRows = 16", "localparam NumberOfRows = " + str(NumberOfRows)
    )
    wrapper_top_str = wrapper_top_str.replace(
        "localparam NumberOfCols = 19", "localparam NumberOfCols = " + str(NumberOfCols)
    )

    # config_str = config_str.replace("parameter NumberOfRows = 16", "parameter NumberOfRows = "+str(NumberOfRows))
    config_str = config_str.replace(
        "RowSelectWidth : integer := 5", f"RowSelectWidth : integer := {RowSelectWidth}"
    )
    config_str = config_str.replace(
        "FrameBitsPerRow : integer := 32;",
        f"FrameBitsPerRow : integer := {FrameBitsPerRow};",
    )
    # config_str = config_str.replace("parameter desync_flag = 20", "parameter desync_flag = "+str(desync_flag))

    configfsm_str = configfsm_str.replace(
        "NumberOfRows : integer := 16;", f"NumberOfRows : integer := {NumberOfRows};"
    )
    configfsm_str = configfsm_str.replace(
        "RowSelectWidth : integer := 5;",
        f"RowSelectWidth : integer := {RowSelectWidth};",
    )
    configfsm_str = configfsm_str.replace(
        "FrameBitsPerRow : integer := 32;",
        f"FrameBitsPerRow : integer := {FrameBitsPerRow};",
    )
    configfsm_str = configfsm_str.replace(
        "desync_flag : integer := 20", f"desync_flag : integer := {desync_flag}"
    )

    testbench_str = testbench_str.replace(
        " STD_LOGIC_VECTOR (32 -1 downto 0)",
        " STD_LOGIC_VECTOR (" + str(NumberOfRows * 2) + " -1 downto 0)",
    )
    testbench_str = testbench_str.replace(
        "STD_LOGIC_VECTOR (64 -1 downto 0)",
        "STD_LOGIC_VECTOR (" + str(NumberOfRows * 4) + " -1 downto 0)",
    )

    # I_top_buf_str = ""
    # T_top_buf_str = ""
    # O_top_buf_str = ""
    # for i in range(NumberOfRows*2):
    # I_top_buf_str += "\tsky130_fd_sc_hd__buf_2 I_top_outbuf_"+str(i)+" (.A(I_top_buf["+str(i)+"]), .X(I_top["+str(i)+"]))\n"
    # T_top_buf_str += "\tsky130_fd_sc_hd__buf_2 T_top_outbuf_"+str(i)+" (.A(T_top_buf["+str(i)+"]), .X(T_top["+str(i)+"]))\n"
    # O_top_buf_str += "\tsky130_fd_sc_hd__buf_2 O_top_inbuf_"+str(i)+" (.A(O_top["+str(i)+"]), .X(O_top_buf["+str(i)+"]))\n"

    # A_config_C_buf_str = ""
    # B_config_C_buf_str = ""
    # for j in range(NumberOfRows*4):
    # A_config_C_buf_str += "\tsky130_fd_sc_hd__buf_2 A_config_C_outbuf_"+str(j)+" (.A(A_config_C_buf["+str(j)+"]), .X(A_config_C["+str(j)+"]))\n"
    # B_config_C_buf_str += "\tsky130_fd_sc_hd__buf_2 B_config_C_outbuf_"+str(j)+" (.A(B_config_C_buf["+str(j)+"]), .X(B_config_C["+str(j)+"]))\n"

    # wrapper_top_str+=I_top_buf_str+'\n'
    # wrapper_top_str+=T_top_buf_str+'\n'
    # wrapper_top_str+=O_top_buf_str+'\n'
    # wrapper_top_str+=A_config_C_buf_str+'\n'
    # wrapper_top_str+=B_config_C_buf_str+'\n'

    for row in range(NumberOfRows):
        data_reg_name = "Frame_Data_Reg_" + str(row)

        wrapper_top_str += f"  Inst_{data_reg_name}: Frame_Data_Reg" "\n"
        wrapper_top_str += f"    generic map (" "\n"
        wrapper_top_str += f"      FrameBitsPerRow => {FrameBitsPerRow}," "\n"
        wrapper_top_str += f"      RowSelectWidth => {RowSelectWidth}," "\n"
        wrapper_top_str += f"      Row => {row+1}" "\n"
        wrapper_top_str += f"    )" "\n"
        wrapper_top_str += f"    port map (" "\n"
        wrapper_top_str += f"      FrameData_I => LocalWriteData," "\n"
        wrapper_top_str += (
            f"      FrameData_O => FrameRegister( {row}*FrameBitsPerRow + FrameBitsPerRow - 1 downto {row}*FrameBitsPerRow ),"
            "\n"
        )
        wrapper_top_str += f"      RowSelect => RowSelect," "\n"
        wrapper_top_str += f"      CLK => CLK" "\n"
        wrapper_top_str += f"    );" "\n\n"

    for col in range(NumberOfCols):
        strobe_reg_name = "Frame_Select_" + str(col)

        wrapper_top_str += f"  Inst_{strobe_reg_name}: Frame_Select" "\n"
        wrapper_top_str += f"    generic map (" "\n"
        wrapper_top_str += f"      FrameSelectWidth => {FrameSelectWidth}," "\n"
        wrapper_top_str += f"      MaxFramesPerCol => {MaxFramesPerCol}," "\n"
        wrapper_top_str += f"      Col => {col}" "\n"
        wrapper_top_str += f"    )" "\n"
        wrapper_top_str += f"    port map (" "\n"
        wrapper_top_str += (
            f"      FrameStrobe_I => FrameAddressRegister(MaxFramesPerCol-1 downto 0),"
            "\n"
        )
        wrapper_top_str += (
            f"      FrameStrobe_O => FrameSelect( MaxFramesPerCol*{col} + MaxFramesPerCol - 1 downto MaxFramesPerCol*{col} ),"
            "\n"
        )
        wrapper_top_str += (
            f"      FrameSelect => FrameAddressRegister(FrameBitsPerRow-1 downto FrameBitsPerRow-(FrameSelectWidth)),"
            "\n"
        )
        wrapper_top_str += f"      FrameStrobe => LongFrameStrobe" "\n"
        wrapper_top_str += f"    );" "\n\n"

    # wrapper_top_str+='\twire ['+str(NumberOfRows-1)+':0] dump\n\n'
    wrapper_top_str += "\tInst_eFPGA: eFPGA\n"
    wrapper_top_str += "  port map (\n"

    I_top_str = ""
    T_top_str = ""
    O_top_str = ""
    count = 0
    for i in range(NumberOfRows * 2 - 1, -1, -2):
        count += 1
        I_top_str += f"    Tile_X0Y{count}_A_I_top => I_top({i})," "\n"
        I_top_str += f"    Tile_X0Y{count}_B_I_top => I_top({i-1})," "\n"

        T_top_str += f"    Tile_X0Y{count}_A_T_top => T_top({i})," "\n"
        T_top_str += f"    Tile_X0Y{count}_B_T_top => T_top({i-1})," "\n"

        O_top_str += f"    Tile_X0Y{count}_A_O_top => O_top({i})," "\n"
        O_top_str += f"    Tile_X0Y{count}_B_O_top => O_top({i-1})," "\n"

    A_config_C_str = ""
    B_config_C_str = ""

    FAB2RAM_C_str = ""
    Config_accessC_str = ""

    count = 0
    for i in range(NumberOfRows * 4 - 1, -1, -4):
        count += 1

        A_config_C_str += (
            f"    Tile_X0Y{count}_A_config_C_bit0 => A_config_C({i})," "\n"
        )
        A_config_C_str += (
            f"    Tile_X0Y{count}_A_config_C_bit1 => A_config_C({i-1})," "\n"
        )
        A_config_C_str += (
            f"    Tile_X0Y{count}_A_config_C_bit2 => A_config_C({i-2})," "\n"
        )
        A_config_C_str += (
            f"    Tile_X0Y{count}_A_config_C_bit3 => A_config_C({i-3})," "\n"
        )

        B_config_C_str += (
            f"    Tile_X0Y{count}_B_config_C_bit0 => B_config_C({i})," "\n"
        )
        B_config_C_str += (
            f"    Tile_X0Y{count}_B_config_C_bit1 => B_config_C({i-1})," "\n"
        )
        B_config_C_str += (
            f"    Tile_X0Y{count}_B_config_C_bit2 => B_config_C({i-2})," "\n"
        )
        B_config_C_str += (
            f"    Tile_X0Y{count}_B_config_C_bit3 => B_config_C({i-3})," "\n"
        )

        FAB2RAM_C_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_C_O0 => FAB2RAM_C({i})," "\n"
        )
        FAB2RAM_C_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_C_O1 => FAB2RAM_C({i-1})," "\n"
        )
        FAB2RAM_C_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_C_O2 => FAB2RAM_C({i-2})," "\n"
        )
        FAB2RAM_C_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_C_O3 => FAB2RAM_C({i-3})," "\n"
        )

        Config_accessC_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_Config_accessC_bit0 => Config_accessC({i}),"
            "\n"
        )
        Config_accessC_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_Config_accessC_bit1 => Config_accessC({i-1}),"
            "\n"
        )
        Config_accessC_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_Config_accessC_bit2 => Config_accessC({i-2}),"
            "\n"
        )
        Config_accessC_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_Config_accessC_bit3 => Config_accessC({i-3}),"
            "\n"
        )

    RAM2FAB_D_str = ""
    FAB2RAM_D_str = ""
    count = 0

    # for i in range(NumberOfRows*4*4-1-12,-1,-15):
    # count += 1
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D0_I0(RAM2FAB_D['+str(i)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D0_I1(RAM2FAB_D['+str(i-1)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D0_I2(RAM2FAB_D['+str(i-2)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D0_I3(RAM2FAB_D['+str(i-3)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D1_I0(RAM2FAB_D['+str(i-4)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D1_I1(RAM2FAB_D['+str(i-5)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D1_I2(dump['+str(NumberOfRows-count)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D1_I3(RAM2FAB_D['+str(i-6)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D2_I0(RAM2FAB_D['+str(i-7)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D2_I1(RAM2FAB_D['+str(i-8)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D2_I2(RAM2FAB_D['+str(i-9)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D2_I3(RAM2FAB_D['+str(i-10)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D3_I0(RAM2FAB_D['+str(i-11)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D3_I1(RAM2FAB_D['+str(i-12)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D3_I2(RAM2FAB_D['+str(i-13)+']),\n'
    # RAM2FAB_D_str+='\t.Tile_X'+str(NumberOfCols-1)+'Y'+str(count)+'_RAM2FAB_D3_I3(RAM2FAB_D['+str(i-14)+']),\n'

    # count = 0
    for i in range(NumberOfRows * 4 * 4 - 1, -1, -16):
        count += 1
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D0_I0 => RAM2FAB_D_Readable({i}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D0_I1 => RAM2FAB_D_Readable({i-1}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D0_I2 => RAM2FAB_D_Readable({i-2}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D0_I3 => RAM2FAB_D_Readable({i-3}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D1_I0 => RAM2FAB_D_Readable({i-4}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D1_I1 => RAM2FAB_D_Readable({i-5}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D1_I2 => RAM2FAB_D_Readable({i-6}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D1_I3 => RAM2FAB_D_Readable({i-7}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D2_I0 => RAM2FAB_D_Readable({i-8}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D2_I1 => RAM2FAB_D_Readable({i-9}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D2_I2 => RAM2FAB_D_Readable({i-10}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D2_I3 => RAM2FAB_D_Readable({i-11}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D3_I0 => RAM2FAB_D_Readable({i-12}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D3_I1 => RAM2FAB_D_Readable({i-13}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D3_I2 => RAM2FAB_D_Readable({i-14}),"
            "\n"
        )
        RAM2FAB_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_RAM2FAB_D3_I3 => RAM2FAB_D_Readable({i-15}),"
            "\n"
        )

        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D0_O0 => FAB2RAM_D({i})," "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D0_O1 => FAB2RAM_D({i-1}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D0_O2 => FAB2RAM_D({i-2}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D0_O3 => FAB2RAM_D({i-3}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D1_O0 => FAB2RAM_D({i-4}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D1_O1 => FAB2RAM_D({i-5}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D1_O2 => FAB2RAM_D({i-6}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D1_O3 => FAB2RAM_D({i-7}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D2_O0 => FAB2RAM_D({i-8}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D2_O1 => FAB2RAM_D({i-9}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D2_O2 => FAB2RAM_D({i-10}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D2_O3 => FAB2RAM_D({i-11}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D3_O0 => FAB2RAM_D({i-12}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D3_O1 => FAB2RAM_D({i-13}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D3_O2 => FAB2RAM_D({i-14}),"
            "\n"
        )
        FAB2RAM_D_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_D3_O3 => FAB2RAM_D({i-15}),"
            "\n"
        )

    FAB2RAM_A_str = ""
    count = 0
    for i in range(NumberOfRows * 4 * 2 - 1, -1, -8):
        count += 1

        FAB2RAM_A_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_A0_O0 => FAB2RAM_A({i})," "\n"
        )
        FAB2RAM_A_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_A0_O1 => FAB2RAM_A({i-1}),"
            "\n"
        )
        FAB2RAM_A_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_A0_O2 => FAB2RAM_A({i-2}),"
            "\n"
        )
        FAB2RAM_A_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_A0_O3 => FAB2RAM_A({i-3}),"
            "\n"
        )
        FAB2RAM_A_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_A1_O0 => FAB2RAM_A({i-4}),"
            "\n"
        )
        FAB2RAM_A_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_A1_O1 => FAB2RAM_A({i-5}),"
            "\n"
        )
        FAB2RAM_A_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_A1_O2 => FAB2RAM_A({i-6}),"
            "\n"
        )
        FAB2RAM_A_str += (
            f"    Tile_X{NumberOfCols-1}Y{count}_FAB2RAM_A1_O3 => FAB2RAM_A({i-7}),"
            "\n"
        )

    wrapper_top_str += I_top_str + "\n"
    wrapper_top_str += T_top_str + "\n"
    wrapper_top_str += O_top_str + "\n"
    wrapper_top_str += A_config_C_str + "\n"
    wrapper_top_str += B_config_C_str + "\n"

    wrapper_top_str += RAM2FAB_D_str + "\n"
    wrapper_top_str += FAB2RAM_D_str + "\n"
    wrapper_top_str += FAB2RAM_A_str + "\n"
    wrapper_top_str += FAB2RAM_C_str + "\n"
    wrapper_top_str += Config_accessC_str + "\n"

    wrapper_top_str += "    --declarations\n"
    wrapper_top_str += "    UserCLK => CLK ,\n"
    wrapper_top_str += "    FrameData => FrameData,\n"
    wrapper_top_str += "    FrameStrobe => FrameSelect \n"
    wrapper_top_str += "    );\n"

    BRAM_str = ""
    data_cap = int((NumberOfRows * 4 * 4) / NumberOfBRAMs)
    addr_cap = int((NumberOfRows * 4 * 2) / NumberOfBRAMs)
    config_cap = int((NumberOfRows * 4) / NumberOfBRAMs)

    # for i in range(NumberOfBRAMs):
    #     BRAM_str += f"  Inst_BlockRAM_{i}: BlockRAM_1KB""\n"
    #     BRAM_str += f"    port map (""\n"
    #     BRAM_str += f"      clk => CLK,""\n"

    #     BRAM_str += f"      rd_addr => FAB2RAM_A({addr_cap*i+8-1} downto {addr_cap*i}),""\n"
    #     BRAM_str += f"      rd_data => RAM2FAB_D_Readable({data_cap*i+32-1} downto {data_cap*i}),""\n"

    #     BRAM_str += f"      wr_addr => FAB2RAM_A({addr_cap * i+16-1} downto {addr_cap*i+8}),""\n"
    #     BRAM_str += f"      wr_data => FAB2RAM_D({data_cap*i+32-1} downto {data_cap*i}),""\n"

    #     BRAM_str += f"      C0 => FAB2RAM_C({config_cap*i}),""\n"
    #     BRAM_str += f"      C1 => FAB2RAM_C({config_cap*i+1}),""\n"
    #     BRAM_str += f"      C2 => FAB2RAM_C({config_cap*i+2}),""\n"
    #     BRAM_str += f"      C3 => FAB2RAM_C({config_cap*i+3}),""\n"
    #     BRAM_str += f"      C4 => FAB2RAM_C({config_cap*i+4}),""\n"
    #     BRAM_str += f"      C5 => FAB2RAM_C({config_cap*i+5})""\n"
    #     BRAM_str += f"    );""\n\n"

    wrapper_top_str += BRAM_str

    # wrapper_top_str += "FrameData <= 16#12345678# & FrameRegister & 16#12345678#;\n\n"
    wrapper_top_str += 'FrameData <= X"12345678" & FrameRegister & X"12345678";'
    wrapper_top_str += "end Behavioral;\n\n"

    # wrapper_top_str+='module sky130_fd_sc_hd__inv (\n'
    # wrapper_top_str+='\tY,\n'
    # wrapper_top_str+='\tA\n'
    # wrapper_top_str+='\t)\n'
    # wrapper_top_str+='\toutput Y\n'
    # wrapper_top_str+='\tinput  A\n'
    # wrapper_top_str+='\n'
    # wrapper_top_str+='\tassign Y=~A\n'
    # wrapper_top_str+='endmodule\n'
    # wrapper_top_str+=data_reg_modules
    # wrapper_top_str+=strobe_reg_modules

    if wrapper_top_str:
        with open(f"{output_dir}/eFPGA_top.vhdl", "w") as file:
            file.write(wrapper_top_str)

    # if data_reg_modules:
    #     with open(f"{output_dir}/Frame_Data_Reg_Pack.vhdl", 'w') as file:
    #         file.write(data_reg_modules)

    # if strobe_reg_modules:
    #     with open(f"{output_dir}/Frame_Select_Pack.vhdl", 'w') as file:
    #         file.write(strobe_reg_modules)

    if config_str:
        with open(f"{output_dir}/Config.vhdl", "w") as file:
            file.write(config_str)

    if configfsm_str:
        with open(f"{output_dir}/ConfigFSM.vhdl", "w") as file:
            file.write(configfsm_str)

    # if testbench_str:
    #    with open("tb_bitbang.vhd", 'w') as file:
    #        file.write(testbench_str)

    print("Finish")


if __name__ == "__main__":

    if sys.version_info <= (3, 5, 0):
        print("Need Python 3.5 or above to run FABulous")
        exit(-1)
    parser = argparse.ArgumentParser(description="")

    parser.add_argument(
        "-o", "--output_dir", help="The directory to the project folder"
    )

    parser.add_argument(
        "-r", "--NumberOfRows", help="The directory to the project folder"
    )

    parser.add_argument(
        "-c", "--NumberOfCols", help="The directory to the project folder"
    )

    parser.add_argument(
        "-b", "--FrameBitsPerRow", help="The directory to the project folder"
    )

    parser.add_argument(
        "-f", "--MaxFramesPerCol", help="The directory to the project folder"
    )

    parser.add_argument(
        "-d", "--desync_flag", help="The directory to the project folder"
    )

    parser.add_argument("-m", "--block_ram", help="The directory to the project folder")

    args = parser.parse_args()

    if args.output_dir:
        output_dir = args.output_dir

    if args.NumberOfRows:
        NumberOfRows = int(args.NumberOfRows)

    if args.NumberOfCols:
        NumberOfCols = int(args.NumberOfCols) + 2

    if args.FrameBitsPerRow:
        FrameBitsPerRow = int(args.FrameBitsPerRow)

    if args.MaxFramesPerCol:
        MaxFramesPerCol = int(args.MaxFramesPerCol)

    if args.desync_flag:
        desync_flag = int(args.desync_flag)

    if args.block_ram:
        NumberOfBRAMs = int(args.block_ram)

    main()

# argv = "/home/ise/shared_folder/diffeq1/LC_on/netgen/synthesis/diffeq_paj_convert_synthesis.v"


# if words[i+1] == "critical":
# number1.append(words[i+3])
# elif x == "Total":
# if words[i+1] == "used":
# number2.append(words[i+5])
# print(number1)
# print(number2)
