# all Directory with in the script will be relative to the project folder
load_fabric
run_FABulous_fabric
gen_user_design_wrapper user_design/top.v user_design/top_wrapper.v
compile_design ./user_design/top.v
run_simulation fst ./user_design/top.bin
exit
