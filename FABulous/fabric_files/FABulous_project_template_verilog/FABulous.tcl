# all Directory with in the script will be relative to the project folder
load_fabric
run_FABulous_fabric
run_FABulous_bitstream ./user_design/sequential_16bit_en.v
run_simulation fst ./user_design/sequential_16bit_en.bin
exit
