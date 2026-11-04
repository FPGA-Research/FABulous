"""Loop-break SDC step.

librelane reads the PnR SDC from `PNR_SDC_FILE`, a path fixed when the flow is
built, but the cuts exist only once the netlist is synthesised. This step writes
the base SDC plus the cuts as the `SDC` view, and `TileAreaOptimisation`, which
runs the tile flow's placement, CTS and routing steps, points `PNR_SDC_FILE` at
it.
"""

from pathlib import Path

from librelane.common.types import Path as ViewPath
from librelane.config.variable import Variable
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.openroad import CheckSDCFiles
from librelane.steps.step import MetricsUpdate, Step, StepException, ViewsUpdate

from fabulous.fabric_cad.gen_sdc import loop_break_nets, render_sdc
from fabulous.fabric_definition.yosys_obj import YosysJson


@Step.factory.register()
class FABulousLoopBreakSDC(Step):
    """Write the PnR SDC with cuts that break the tile's combinational loops.

    The cuts come from `loop_break_nets` on the synthesised netlist, with the
    standard cells modelled from the `SYNTH_CORNER` cell libraries. They are
    appended to `PNR_SDC_FILE`, or to `FALLBACK_SDC` when that is unset.
    """

    id = "FABulous.LoopBreakSDC"
    name = "Loop-Break SDC"
    long_name = "Generate Loop-Break SDC"

    inputs = [DesignFormat.NETLIST]
    outputs = [DesignFormat.SDC]

    config_vars = [
        *CheckSDCFiles.config_vars,
        Variable(
            "FABULOUS_BEL_MODULES",
            list[str] | None,
            "Yosys module selection patterns matching the tile's BELs. Each BEL "
            "must survive synthesis as its own module, so the loop-break cuts "
            "never land inside a BEL.",
        ),
    ]

    def run(self, state_in: State, **_kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Write the loop-break SDC; raise if `FABULOUS_BEL_MODULES` is unset."""
        bel_modules = self.config["FABULOUS_BEL_MODULES"]
        if bel_modules is None:
            raise StepException(
                "FABULOUS_BEL_MODULES is not set, so the loop-break cuts cannot "
                "keep clear of the BELs. The FABulous tile flows set it from the "
                "tile definition."
            )
        design_name = self.config["DESIGN_NAME"]
        liberty = self.toolbox.filter_views(
            self.config, self.config["CELL_LIBS"], self.config.get("SYNTH_CORNER")
        )
        netlist = YosysJson.from_netlist(
            Path(str(state_in[DesignFormat.NETLIST])),
            liberty=liberty,
            top=design_name,
            json_output=Path(self.step_dir) / f"{design_name}.json",
        )
        nets = loop_break_nets(netlist, top=design_name, bel_modules=set(bel_modules))

        base_sdc = Path(self.config["PNR_SDC_FILE"] or self.config["FALLBACK_SDC"])
        sdc = Path(self.step_dir) / f"{design_name}.sdc"
        sdc.write_text(
            render_sdc(
                base_sdc=base_sdc.read_text(), nets=nets, design_name=design_name
            )
        )
        return {DesignFormat.SDC: ViewPath(sdc)}, {
            "timing__loop_break__count": len(nets)
        }
