"""Auto-diode insertion step for FABulous fabric generator."""

import sys
from pathlib import Path

from librelane.config.variable import Variable
from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from FABulous.fabric_generator.gds_generator.steps.while_step import WhileStep


@Step.factory.register()
class AutoEcoDiodeInsertion(WhileStep):
    """Diode iterative diode insertion step."""

    id = "FABulous.AutoDiode"
    name = "FABulous Auto Diode Insertion"

    Steps = [
        Odb.InsertECODiodes,
        OpenROAD.CheckAntennas,
    ]

    config_vars = [
        Variable(
            "AUTO_ECO_DIODE_INSERT_MODE",
            str,
            "Mode for diode insertion, options are 'none', 'ratio' or 'all'. "
            "'ratio' inserts diodes based on the ratio of partial to required antenna "
            "area, 'all' inserts diodes for all violating pins, "
            "'none' inserts no diodes. Default is 'all'.",
            default="all",
        )
    ]

    previous_state: State
    current_iteration: int = 0
    max_iterations: int = sys.maxsize
    done_enough: bool = False

    def condition(self, state: State) -> bool:  # noqa: ARG002
        """Continue looping until no more diodes need to be inserted."""
        return not self.done_enough

    def parse_diodes(self, report: str) -> list[Odb.ECODiode]:
        """Parse the antenna report to determine which diodes to insert.

        Parameters
        ----------
        report : str
            The content of the antenna report file.

        Returns
        -------
        list[Odb.ECODiode]
            A list of ECO diodes to insert based on the report.
        """
        report_line = [i for i in report.splitlines() if i.strip()]
        entry_set = set()
        for line in report_line[3:-1]:
            _, partial, required, net, pin, _ = [
                i.strip() for i in line.split("│") if i.strip()
            ]
            partial = float(partial)
            required = float(required)

            if (partial > required) or (
                self.config["AUTO_ECO_DIODE_INSERT_MODE"] == "all"
            ):
                entry_set.add(f"{pin}")

        to_insert: list[Odb.ECODiode] = [Odb.ECODiode(target=net) for net in entry_set]
        return to_insert

    def pre_iteration_callback(self, pre_iteration: State) -> State:
        """Prepare for the next iteration by updating the config with new diodes."""
        if self.current_iteration == 0:
            OpenROAD.CheckAntennas(self.config, pre_iteration).start(
                step_dir=str(Path(self.step_dir) / "pre-check"),
            )

            report: str = (
                Path(self.step_dir) / "pre-check" / "reports" / "antenna_summary.rpt"
            ).read_text()
        else:
            report: str = (
                Path(self.step_dir)
                / f"iter_{self.current_iteration - 1}"
                / "1-openroad-checkantennas"
                / "reports"
                / "antenna_summary.rpt"
            ).read_text()

        to_insert: list[Odb.ECODiode] = self.parse_diodes(report)
        info(f"Inserting {len(to_insert)} ECO diodes")
        self.config = self.config.copy(INSERT_ECO_DIODES=to_insert)
        if len(to_insert) == 0:
            self.done_enough = True
            info("No more diodes to insert, ending insertion with a final report.")
        return self.previous_state

    def post_iteration_callback(
        self, post_iteration: State, full_iteration: bool
    ) -> State:
        """Update iteration state after running a full iteration.

        If the iteration completed successfully, advance counters and record the
        previous state.
        """
        if full_iteration:
            self.previous_state = post_iteration
            self.current_iteration += 1
        else:
            raise RuntimeError("Fail to insert ECO diodes")
        return post_iteration

    def post_loop_callback(self, state: State) -> State:
        """Post-loop cleanup.

        Currently unimplemented.
        """
        if self.config["AUTO_ECO_DIODE_INSERT_MODE"] == "all" and (
            (state.metrics["antenna__violating__nets"] > 1)
            or (state.metrics["antenna__violating__pins"] > 1)
        ):
            raise RuntimeError("Antenna violations remain after auto-diode insertion.")
        return state

    def run(
        self,
        state_in: State,
        **_kwargs: dict,
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the step, initializing previous_state before looping."""
        if self.config["AUTO_ECO_DIODE_INSERT_MODE"] == "none":
            info("AUTO_ECO_DIODE_INSERT_MODE is 'none', skipping diode insertion.")
            return {}, {}

        self.previous_state = state_in
        return super().run(state_in)
