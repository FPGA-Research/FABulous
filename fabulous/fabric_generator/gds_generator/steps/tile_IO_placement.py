"""Custom IO placement step for FABulous tiles."""

import pathlib
from importlib import resources
from typing import Literal

import yaml
from librelane.common.types import Path
from librelane.config.variable import Variable
from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps.common_variables import (
    io_layer_variables,
)
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import (
    MetricsUpdate,
    Step,
    ViewsUpdate,
)

from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    apply_interface_order,
    read_interface_order,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    TILE_INTERFACE_ORDER_VARIABLE,
)


def _migrate_unmatched_io(x: object) -> str:
    return "unmatched_design" if x else "none"


@Step.factory.register()
class FABulousTileIOPlacement(OdbpyStep):
    """Place I/O pins using a custom script.

    This step uses a custom Python script to place I/O pins according to a user-defined
    configuration file. With `FABULOUS_TILE_INTERFACE_ORDER` set, the listed pins lead
    each border in the listed order before the script runs, which is the one place a
    tile interface order meets a pin configuration.
    """

    id = "Odb.FABulousTileIOPlacement"
    name = "FABulous I/O Placement"
    long_name = "FABulous I/O Pin Placement Script"

    config_vars = io_layer_variables + [
        Variable(
            "FABULOUS_IO_PIN_ORDER_CFG",
            Path | None,
            "Path to a custom pin configuration file.",
            default=None,
        ),
        TILE_INTERFACE_ORDER_VARIABLE,
        Variable(
            "ERRORS_ON_UNMATCHED_IO",
            Literal["none", "unmatched_design", "unmatched_cfg", "both"],
            "Controls whether to emit an error in: no situation, when pins exist in "
            "the design that do not exist in the config file, when pins exist in the "
            "config file that do not exist in the design, and both respectively. "
            "`both` is recommended, as the default is only for backwards compatibility "
            "with librelane 1.",
            default="unmatched_design",  # Backwards compatible with librelane 1
            deprecated_names=[
                ("QUIT_ON_UNMATCHED_IO", _migrate_unmatched_io),
            ],
        ),
    ]

    def get_script_path(self) -> str:
        """Get the path to the I/O placement script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "tile_io_place.py"
        )

    def get_command(self) -> list[str]:
        """Get the command to run the I/O placement script."""
        length_args = []
        if self.config["IO_PIN_V_LENGTH"] is not None:
            length_args += ["--ver-length", self.config["IO_PIN_V_LENGTH"]]
        if self.config["IO_PIN_H_LENGTH"] is not None:
            length_args += ["--hor-length", self.config["IO_PIN_H_LENGTH"]]

        return (
            super().get_command()
            + [
                "--config",
                str(self.pin_config_path()),
                "--hor-layer",
                self.config["IO_PIN_H_LAYER"],
                "--ver-layer",
                self.config["IO_PIN_V_LAYER"],
                "--hor-width-mult",
                str(self.config["IO_PIN_H_THICKNESS_MULT"]),
                "--ver-width-mult",
                str(self.config["IO_PIN_V_THICKNESS_MULT"]),
                "--hor-extension",
                str(self.config["IO_PIN_H_EXTENSION"]),
                "--ver-extension",
                str(self.config["IO_PIN_V_EXTENSION"]),
                "--unmatched-error",
                self.config["ERRORS_ON_UNMATCHED_IO"],
            ]
            + length_args
        )

    def pin_config_path(self) -> pathlib.Path:
        """Return the pin configuration the script reads, ordered when an order is set.

        Returns
        -------
        pathlib.Path
            `FABULOUS_IO_PIN_ORDER_CFG` itself, or its reordered copy in the
            step directory when `FABULOUS_TILE_INTERFACE_ORDER` is set.

        Raises
        ------
        ValueError
            If no pin configuration is set.
        """
        io_pin_order_cfg = self.config["FABULOUS_IO_PIN_ORDER_CFG"]
        if io_pin_order_cfg is None:
            raise ValueError(
                "FABULOUS_IO_PIN_ORDER_CFG must be set before IO placement"
            )
        source = pathlib.Path(str(io_pin_order_cfg))
        order_path = self.config[TILE_INTERFACE_ORDER_VARIABLE.name]
        if order_path is None:
            return source
        order = read_interface_order(pathlib.Path(str(order_path)))
        payload = apply_interface_order(yaml.safe_load(source.read_text()), order)
        ordered = (
            pathlib.Path(self.step_dir)
            / f"{self.config['DESIGN_NAME']}_io_pin_order.yaml"
        )
        ordered.write_text(yaml.safe_dump(payload))
        info(f"Pin configuration follows the interface order {order_path}: {ordered}")
        return ordered

    def run(self, state_in: State, **kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the I/O placement step."""
        return super().run(state_in, **kwargs)
