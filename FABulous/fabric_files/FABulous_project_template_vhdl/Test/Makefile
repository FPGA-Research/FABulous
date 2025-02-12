MAX_BITBYTES=16384
FAB_PROJ_ROOT=..
BUILD_DIR=build
DESIGN=sequential_16bit_en
TESTBENCH=${DESIGN}_tb
TOP_WRAPPER=top_wrapper

USER_DESIGN_DIR=${FAB_PROJ_ROOT}/user_design
USER_DESIGN_VHDL=${USER_DESIGN_DIR}/${DESIGN}.vhdl
TOP_WRAPPER_VERILOG=${USER_DESIGN_DIR}/${TOP_WRAPPER}.v # Still needs to be verilog, since it is more like a constraint file for yosys
FAB_TILE_FOLDER=${FAB_PROJ_ROOT}/Tile
FAB_FABRIC_FOLDER=${FAB_PROJ_ROOT}/Fabric

GHDL=ghdl
GHDL_FLAGS=--std=08 -O2 --workdir=${BUILD_DIR}

.PHONY: all run_FABulous_demo full build_test_design run_simulation mkdir_build clean

sim: build_test_design run_simulation clean

full_sim: run_FABulous_demo build_test_design run_simulation clean

build_test_design: run_yosys run_nextpnr run_bitgen

run_FABulous_demo:
	# Runs FABulous, generates the default fabric.
	FABulous ${FAB_PROJ_ROOT} -fs ${FAB_PROJ_ROOT}/FABulous.tcl

run_yosys: mkdir_build
	yosys -m ghdl -p "ghdl ${USER_DESIGN_VHDL} -e ${DESIGN}; read_verilog ${TOP_WRAPPER_VERILOG}; synth_fabulous -top ${TOP_WRAPPER} -json ${BUILD_DIR}/${DESIGN}.json;"

run_nextpnr: mkdir_build
	FAB_ROOT=${FAB_PROJ_ROOT} nextpnr-generic --uarch fabulous --json ${BUILD_DIR}/${DESIGN}.json -o fasm=${BUILD_DIR}/${DESIGN}.fasm

run_bitgen: mkdir_build
	bit_gen -genBitstream ${BUILD_DIR}/${DESIGN}.fasm ${FAB_PROJ_ROOT}/.FABulous/bitStreamSpec.bin ${BUILD_DIR}/${DESIGN}.bin
	python3 makehex.py ${BUILD_DIR}/${DESIGN}.bin ${MAX_BITBYTES} ${BUILD_DIR}/${DESIGN}.hex

mkdir_build:
	mkdir -p ${BUILD_DIR}

run_GTKWave:
	gtkwave ${BUILD_DIR}/${DESIGN}.fst

clean:
	rm -rf ${BUILD_DIR}

run_simulation: mkdir_build
	ulimit -s unlimited && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/my_lib.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/LUT4AB/LUT4AB_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/LUT4AB/LUT4AB_ConfigMem.vhdl \
	              ${FAB_TILE_FOLDER}/LUT4AB/LUT4c_frame_config.vhdl \
	              ${FAB_TILE_FOLDER}/LUT4AB/MUX8LUT_frame_config.vhdl \
	              ${FAB_TILE_FOLDER}/LUT4AB/LUT4AB.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/RAM_IO/RAM_IO_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/RAM_IO/RAM_IO_ConfigMem.vhdl \
	              ${FAB_TILE_FOLDER}/RAM_IO/InPass4_frame_config.vhdl \
	              ${FAB_TILE_FOLDER}/RAM_IO/OutPass4_frame_config.vhdl \
	              ${FAB_TILE_FOLDER}/RAM_IO/RAM_IO.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/RegFile/RegFile_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/RegFile/RegFile_ConfigMem.vhdl \
	              ${FAB_TILE_FOLDER}/RegFile/RegFile_32x4.vhdl \
	              ${FAB_TILE_FOLDER}/RegFile/RegFile.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/W_IO/W_IO_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/W_IO/W_IO_ConfigMem.vhdl \
	              ${FAB_TILE_FOLDER}/W_IO/IO_1_bidirectional_frame_config_pass.vhdl \
	              ${FAB_TILE_FOLDER}/W_IO/Config_access.vhdl \
	              ${FAB_TILE_FOLDER}/W_IO/W_IO.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/DSP/DSP_top/DSP_top_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/DSP/DSP_top/DSP_top_ConfigMem.vhdl \
	              ${FAB_TILE_FOLDER}/DSP/DSP_top/DSP_top.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/DSP/DSP_bot/DSP_bot_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/DSP/DSP_bot/DSP_bot_ConfigMem.vhdl \
	              ${FAB_TILE_FOLDER}/DSP/DSP_bot/MULADD.vhdl \
	              ${FAB_TILE_FOLDER}/DSP/DSP_bot/DSP_bot.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/DSP/DSP_top/DSP_top.vhdl \
	                ${FAB_TILE_FOLDER}/DSP/DSP_bot/DSP_bot.vhdl \
	                ${FAB_TILE_FOLDER}/DSP/DSP.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/N_term_DSP/N_term_DSP_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/N_term_DSP/N_term_DSP.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/S_term_DSP/S_term_DSP_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/S_term_DSP/S_term_DSP.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/N_term_RAM_IO/N_term_RAM_IO_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/N_term_RAM_IO/N_term_RAM_IO.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/S_term_RAM_IO/S_term_RAM_IO_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/S_term_RAM_IO/S_term_RAM_IO.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/N_term_single/N_term_single_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/N_term_single/N_term_single.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/S_term_single/S_term_single_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/S_term_single/S_term_single.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/N_term_single2/N_term_single2_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/N_term_single2/N_term_single2.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_TILE_FOLDER}/S_term_single2/S_term_single2_switch_matrix.vhdl \
	              ${FAB_TILE_FOLDER}/S_term_single2/S_term_single2.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/config_UART.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/bitbang.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/ConfigFSM.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/eFPGA_Config.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/Frame_Data_Reg.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/Frame_Select.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/BlockRAM_1KB.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/eFPGA.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${FAB_FABRIC_FOLDER}/eFPGA_top.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${USER_DESIGN_DIR}/${DESIGN}.vhdl && \
	${GHDL} -a ${GHDL_FLAGS} ${TESTBENCH}.vhdl && \
	${GHDL} -e ${GHDL_FLAGS} -fexplicit ${TESTBENCH} && \
	${GHDL} -r ${GHDL_FLAGS} ${TESTBENCH} --stats --ieee-asserts=disable --fst=${BUILD_DIR}/${TESTBENCH}.fst
