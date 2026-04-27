"""Defines the base class for architecture synthesizers.

This module defines the `ArchitectureSynthesizer` abstract base class, which
serves as a blueprint for synthesizers that generate FPGA architectures.
"""

from abc import ABC, abstractmethod

from loguru import logger

from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.design_analyzer_pass import (
    DesignAnalyzerPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_combinator_pass import (
    LutCombinatorPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import (
    PyosysBridge,
)


class ArchitectureSynthesizer(ABC):
    """Interface for architecture-specific synthesis pipelines.

    Parameters
    ----------
    debug : bool
        Enable debug mode for verbose logging and intermediate design dumps.
    """

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self.design: PyosysBridge = PyosysBridge(debug=self.debug)

        # Custom passes for design analysis and optimization

        self.design_analyzer_pass = DesignAnalyzerPass
        self.lut_combinator_pass = LutCombinatorPass

    def log_info(self, message: str) -> None:
        """Log an informational message.

        Parameters
        ----------
        message : str
            The message to log.
        """
        logger.info(message)

    @abstractmethod
    def synthesize(self) -> None:
        """Run the full synthesis pipeline for a user design."""

    @abstractmethod
    def generate_primitives(self) -> None:
        """Generate primitive definitions required by this architecture."""

    @abstractmethod
    def generate_switch_matrix(self) -> None:
        """Generate switch-matrix resources for routing integration."""
