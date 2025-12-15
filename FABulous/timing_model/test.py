from pathlib import Path
from  FABulous_timing_model import FABulousTileTimingModel
from FABulous_timing_model_interface import FABulousTimingModelInterface

if __name__ == "__main__":
    #sdf_graph = FABulousTileTimingModel(config={
    #    "project_dir": Path("/home/hausding/timing_model_v4/FABulous/demo1"),
    #    "liberty_files": Path("/home/hausding/.ciel/ciel/ihp-sg13g2/versions/cb7daaa8901016cf7c5d272dfa322c41f024931f/ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib"),
    #    "tile_name": "DSP",
    #    "super_tile_type": "bot",
    #    "techmap_files": [Path("/home/hausding/.ciel/ciel/ihp-sg13g2/versions/cb7daaa8901016cf7c5d272dfa322c41f024931f/ihp-sg13g2/libs.tech/librelane/sg13g2_stdcell/latch_map.v"), Path("/home/hausding/.ciel/ciel/ihp-sg13g2/versions/cb7daaa8901016cf7c5d272dfa322c41f024931f/ihp-sg13g2/libs.tech/librelane/sg13g2_stdcell/tribuff_map.v")],
    #    "min_buf_cell_and_ports": "sg13g2_buf_1 A X",
    #    "mode": "physical",
    #})
    
    fiface = FABulousTimingModelInterface(config={
        "project_dir": Path("/home/hausding/timing_model_v4/FABulous/demo1"),
        "liberty_files": Path("/home/hausding/.ciel/ciel/ihp-sg13g2/versions/cb7daaa8901016cf7c5d272dfa322c41f024931f/ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib"),
        "tile_name": "DSP",
        "super_tile_type": "bot",
        "techmap_files": [Path("/home/hausding/.ciel/ciel/ihp-sg13g2/versions/cb7daaa8901016cf7c5d272dfa322c41f024931f/ihp-sg13g2/libs.tech/librelane/sg13g2_stdcell/latch_map.v"), Path("/home/hausding/.ciel/ciel/ihp-sg13g2/versions/cb7daaa8901016cf7c5d272dfa322c41f024931f/ihp-sg13g2/libs.tech/librelane/sg13g2_stdcell/tribuff_map.v")],
        "min_buf_cell_and_ports": "sg13g2_buf_1 A X",
        "mode": "physical",
    })
    #delay = sdf_graph.pip_delay("J2END_AB_END2","A2")
    #delay = sdf_graph.pip_delay("LD_O","JE2BEG1")
    #delay = sdf_graph.pip_delay("LE_O","JE2BEG1")
    #delay = sdf_graph.pip_delay("LF_O","JE2BEG1")
    #delay = sdf_graph.pip_delay("LG_O","JE2BEG1")
    #s = sdf_graph.hdlnx_tm_synth.find_verilog_modules_regex(r".*_switch_matrix")
    #print(s)
    
    