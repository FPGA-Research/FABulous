"""Ad-hoc tests."""

from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.synthesizer.core.fabulous_architecture import (
    FabulousArchitecture,
)
from fabulous.fabric_cad.fabxplore.synthesizer.core.models import (
    FabulousArchitectureConfig,
)
from fabulous.fabulous_cli.helper import (
    setup_logger,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "tests" / "synthesizer" / "out"
setup_logger(verbosity=0, debug=False)


def test_basic_synth_flow() -> None:
    """Test the basic synthesis flow of the FABulousArchitecture."""
    logger.info("Testing basic synthesis flow of FABulousArchitecture")
    hdl_files = [ROOT / "benchmarks" / "verilog_rtl" / "ode" / "ode.v"]
    config = FabulousArchitectureConfig(
        hdl_files=hdl_files,
        top_module="ode",
        allow_resource_sharing=True,
        map_alu_macc_cells=True,
        map_ram_cells=True,
        optimize_fsm=True,
        map_io_pads=True,
        map_carry_chains=True,
        user_design_out_dir=OUT_DIR,
    )
    arch = FabulousArchitecture(config, debug=True)
    arch.synthesize()
    arch.write_verilog_path()
    arch.write_json_path()


def main() -> None:
    """Run all tests."""
    sel_test: int = 0

    match sel_test:
        case 0:
            test_basic_synth_flow()


if __name__ == "__main__":
    """Run all tests."""
    main()
