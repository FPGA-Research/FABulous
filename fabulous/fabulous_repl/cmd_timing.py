"""Timing-model characterization command for the FABulous REPL.

Generate the nextpnr timing model for the fabric.
"""

from pathlib import Path
from typing import Annotated, Literal

from cmd2 import with_annotated, with_category
from cmd2.annotated import Option
from loguru import logger

from fabulous.fabric_cad.timing_model.models import (
    TimingModelConfig,
    TimingModelMode,
    TimingModelTileSourceFiles,
)
from fabulous.fabulous_repl.command_set_base import (
    CMD_TIMING_MODEL,
    ReplCommandSet,
)
from fabulous.fabulous_settings import get_context


class TimingCommandSet(ReplCommandSet):
    """Generate the nextpnr timing model for the fabric."""

    @with_category(CMD_TIMING_MODEL)
    @with_annotated
    def do_timing_model(
        self,
        mode: Annotated[
            Literal["physical", "structural"],
            Option(
                "--mode",
                help_text="Timing model generation mode (physical or structural).",
            ),
        ] = "physical",
        outfile: Annotated[
            Path | None,
            Option(
                "--outfile",
                help_text=(
                    "Output file for the generated timing model or config template."
                ),
            ),
        ] = None,
        emit_config_template: Annotated[
            bool,
            Option(
                "--emit-config-template",
                help_text=(
                    "Output file for the generated timing model config template."
                ),
            ),
        ] = False,
        with_config_file: Annotated[
            Path | None,
            Option(
                "--with-config-file",
                help_text=(
                    "Use a config file for timing model generation "
                    "instead of command arguments."
                ),
            ),
        ] = None,
    ) -> None:
        """Generate a timing model for the fabric.

        Timing information is extracted from the GDS layout and used to create a timing
        model compatible with nextpnr for timing-aware place and route. This command
        generates a timing model for the FPGA fabric based on the specified mode
        (physical or structural) and outputs it to a file named pips.txt in the
        .FABulous directory. If no config file is provided, the automated flow must be
        run first to generate post-layout files. If a config file is provided, it will
        be used for timing model generation instead of command arguments. This allows
        for more complex configurations like different PDK support. If
        emit-config-template is specified, a config template will be output and no
        timing model will be generated.
        """
        repl = self._cmd
        manual_config: TimingModelConfig | None = None

        # Custom output path for the timing model file, if not provided, defaults
        # to .FABulous/pips.txt with backup of existing file if exists.
        resolved_outfile: Path
        if outfile is not None:
            resolved_outfile = outfile
        else:
            pips_path = get_context().proj_dir / ".FABulous" / "pips.txt"
            if pips_path.exists():
                backup_path = pips_path.with_suffix(".backup.txt")
                logger.info(f"Backing up existing pips.txt to {backup_path}")
                pips_path.rename(backup_path)
            resolved_outfile = pips_path

        # If a config file is provided, use it to generate the timing model
        # instead of command arguments This allows for more complex configurations
        # like supporting different PDKs.
        if with_config_file is not None:
            if not with_config_file.exists():
                raise FileNotFoundError(f"Config file {with_config_file} not found")
            manual_config = TimingModelConfig.model_validate_json(
                with_config_file.read_text()
            )

        # If emit-config-template is specified, output a config template
        # and return without generating the timing model.
        if emit_config_template:
            cfg_template: TimingModelConfig = TimingModelConfig(
                project_dir=get_context().proj_dir,
                liberty_files=Path("path/to/liberty/files: <required>"),
                min_buf_cell_and_ports="cell_name in_port out_port: <required>",
                synth_executable=get_context().yosys_path,
                sta_executable=get_context().opensta_path,
                mode=TimingModelMode(mode),
                custom_per_tile_source_files=dict.fromkeys(
                    repl.all_tile,
                    TimingModelTileSourceFiles(
                        netlist_file=Path(
                            "path/to/netlist: <optional, not use project dir files>"
                        ),
                        rc_file=Path(
                            "path/to/rc: <optional, not use project dir files>"
                        ),
                        rtl_files=[
                            Path("path/to/rtl: <optional, not use project dir files>")
                        ],
                    ),
                ),
            )

            template_outfile = (
                outfile
                if outfile is not None
                else (
                    get_context().proj_dir
                    / ".FABulous"
                    / "timing_model_config_template.json"
                )
            )
            template_outfile.write_text(cfg_template.model_dump_json(indent=4))
            logger.info(f"Timing model config template generated at {template_outfile}")
            return

        logger.info(f"Output timing model file: {resolved_outfile}")

        tm_config_resolved: TimingModelConfig = repl.fabulousAPI.timing_model_interface(
            mode=mode,
            output_file=resolved_outfile,
            debug=repl.debug,
            manual_config=manual_config,
        )

        resolved_path: Path = (
            get_context().proj_dir / ".FABulous" / "timing_model_config_resolved.json"
        )
        resolved_path.write_text(tm_config_resolved.model_dump_json(indent=4))
        logger.info(f"Timing model config resolved at {resolved_path}")
