MAX_BITBYTES=16384
FAB_PROJ_ROOT=..
BUILD_DIR=build
DESIGN=sequential_16bit_en
TESTBENCH=${DESIGN}_tb
TOP_WRAPPER=top_wrapper

FABRIC_FILES_DIR=${BUILD_DIR}/fabric_files
USER_DESIGN_DIR=${FAB_PROJ_ROOT}/user_design
USER_DESIGN_VERILOG=${USER_DESIGN_DIR}/${DESIGN}.v
TOP_WRAPPER_VERILOG=${USER_DESIGN_DIR}/${TOP_WRAPPER}.v
WAVEFORM_TYPE=fst

VVP_ARGS=+output_waveform=${BUILD_DIR}/${DESIGN}.${WAVEFORM_TYPE}
VVP_ARGS+=+bitstream_hex=${BUILD_DIR}/${DESIGN}.hex
ifeq ($(WAVEFORM_TYPE),fst)
    VVP_ARGS+=-fst
endif

.PHONY: all run_FABulous_demo full build_test_design run_simulation_emulation mkdir_build clean

sim: build_test_design run_simulation clean

FAB_sim: build_demo_fabric build_test_design run_simulation clean

full_sim: run_FABulous_demo build_test_design run_simulation_emulation clean

build_test_design: run_yosys run_nextpnr run_bitgen copy_files

run_simulation_emulation: run_emulation run_simulation

run_FABulous_demo:
	# Runs FABulous, generates the default fabric and generates a bitstream from the default user_design.
	# Create build folders, since FABulous removes them after it runs its simulation.
	FABulous ${FAB_PROJ_ROOT} -fs ${FAB_PROJ_ROOT}/FABulous.tcl
	mkdir -p ${BUILD_DIR}
	mkdir -p ${FABRIC_FILES_DIR}
	mv -f ${DESIGN}.hex ${BUILD_DIR}/
	mv -f ${DESIGN}.fst ${BUILD_DIR}/
	cp -fu ${USER_DESIGN_DIR}/* ${BUILD_DIR}

build_demo_fabric: mkdir_build
	# Builds the default fabric
	FABulous ${FAB_PROJ_ROOT} -ts ./build_fabulous_fabric.tcl

run_yosys: mkdir_build
	yosys -p "synth_fabulous -top ${TOP_WRAPPER} -json ${BUILD_DIR}/${DESIGN}.json" ${USER_DESIGN_VERILOG} ${TOP_WRAPPER_VERILOG}

run_nextpnr: mkdir_build
	FAB_ROOT=${FAB_PROJ_ROOT} nextpnr-generic --uarch fabulous --json ${BUILD_DIR}/${DESIGN}.json -o fasm=${BUILD_DIR}/${DESIGN}.fasm

run_bitgen: mkdir_build
	bit_gen -genBitstream ${BUILD_DIR}/${DESIGN}.fasm ${FAB_PROJ_ROOT}/.FABulous/bitStreamSpec.bin ${BUILD_DIR}/${DESIGN}.bin
	python3 makehex.py ${BUILD_DIR}/${DESIGN}.bin ${MAX_BITBYTES} ${BUILD_DIR}/${DESIGN}.hex

copy_files: mkdir_build
	find ${FAB_PROJ_ROOT}/Tile/ -name '*.v' -type f -print0 | xargs -0 cp -u -t ./${FABRIC_FILES_DIR}/
	find ${FAB_PROJ_ROOT}/Fabric/ -name '*.v' -type f -print0 | xargs -0 cp -u -t ./${FABRIC_FILES_DIR}/

mkdir_build:
	mkdir -p ${BUILD_DIR}
	mkdir -p ${FABRIC_FILES_DIR}

run_simulation:
	iverilog -s ${TESTBENCH} -o ${BUILD_DIR}/${DESIGN}.vvp ${FABRIC_FILES_DIR}/* ${USER_DESIGN_VERILOG} ${TESTBENCH}.v -g2012
	vvp ${BUILD_DIR}/${DESIGN}.vvp ${VVP_ARGS}

run_emulation:
	iverilog -D EMULATION -s ${TESTBENCH} -o ${BUILD_DIR}/${DESIGN}.vvp ${BUILD_DIR}/${DESIGN}.vh ${FABRIC_FILES_DIR}/* ${USER_DESIGN_VERILOG} ${TESTBENCH}.v -g2012
	vvp ${BUILD_DIR}/${DESIGN}.vvp ${VVP_ARGS}

run_GTKWave:
	gtkwave ${BUILD_DIR}/${DESIGN}.${WAVEFORM_TYPE}

clean:
	rm -rf ${BUILD_DIR}
