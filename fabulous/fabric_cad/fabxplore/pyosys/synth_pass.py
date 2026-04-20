"""Module defining the SynthPass abstract base class for synthesis passes in Pyosys.

This module provides the SynthPass abstract base class, which defines the interface for
synthesis passes that can be applied to a design represented by the PyosysBridge.
"""

from abc import ABC, abstractmethod

from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class SynthPass(ABC):
    """Abstract base class for synthesis passes in Pyosys."""

    @abstractmethod
    def run_on(self, design: PyosysBridge) -> None:
        """Run the synthesis pass on the given design.

        Parameters
        ----------
        design : PyosysBridge
            The design to be processed by the synthesis pass.
        """

    @property
    @abstractmethod
    def report_summary(self) -> str:
        """Return a summary report of the synthesis pass results."""

    @property
    @abstractmethod
    def result_data(self) -> object | None:
        """Return any relevant data from the synthesis pass results.

        Returns
        -------
        object | None
            Data relevant to the synthesis pass results, or None if not available.
        """
