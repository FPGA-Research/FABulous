"""Per-cell techmap renderers for the chain mapper.

Each class in this module owns the template context and rendering for exactly one Yosys
source cell type. The top-level chain mapper uses these objects as small plugins, so
adding a new chain-capable operation only requires adding another cell renderer and
registering it in the mapper.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.models import (
    AluInitMode,
    ChainMapperConfig,
)
from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.templates import (
    ALU_TECHMAP_TEMPLATE,
    REDUCE_AND_TECHMAP_TEMPLATE,
    REDUCE_BOOL_TECHMAP_TEMPLATE,
    REDUCE_OR_TECHMAP_TEMPLATE,
    REDUCE_XOR_TECHMAP_TEMPLATE,
    TEMPLATE_ENV,
)


@dataclass(frozen=True)
class ChainCellTechmap(ABC):
    """Abstract interface for one generated chain techmap file.

    Parameters
    ----------
    config : ChainMapperConfig
        Shared chain mapper configuration.

    Attributes
    ----------
    config : ChainMapperConfig
        Shared chain mapper configuration.
    """

    config: ChainMapperConfig

    @property
    @abstractmethod
    def module_name(self) -> str:
        """Return the generated techmap module name."""

    @abstractmethod
    def render(self) -> tuple[str, str]:
        """Render this cell's techmap file.

        Returns
        -------
        tuple[str, str]
            ``(module_name, verilog)`` pair suitable for a ``techmap -map`` file.
        """

    def _render_template(
        self,
        template: str,
        context: dict[str, object],
    ) -> tuple[str, str]:
        """Render a template with common chain mapper parameters.

        Parameters
        ----------
        template : str
            Verilog techmap template.
        context : dict[str, object]
            Cell-specific template values.

        Returns
        -------
        tuple[str, str]
            ``(module_name, verilog)`` pair.
        """
        return (
            self.module_name,
            TEMPLATE_ENV.from_string(template).render(
                chain_name=self.config.chain_name,
                chunk_size=self.config.chunk_size,
                effective_min_chain_prims=(
                    self.config.min_chain_prims if self.config.leave_short else 1
                ),
                max_chain_prims_value=self.config.max_chain_prims or 0,
                **context,
            ),
        )


@dataclass(frozen=True)
class ReduceAndTechmap(ChainCellTechmap):
    """Render the ``$reduce_and`` chain techmap.

    This renderer maps AND reductions either directly to AND-mode chain primitives or,
    when configured, through an OR chain using De Morgan inversion. Tail chunks are
    padded with the identity value for the physical mode selected by the context.
    """

    @property
    def module_name(self) -> str:
        """Return the generated techmap module name.

        Returns
        -------
        str
            Generated Verilog module name used by the ``techmap`` file.
        """
        return "_chain_reduce_and"

    def render(self) -> tuple[str, str]:
        """Render the ``$reduce_and`` techmap file.

        Returns
        -------
        tuple[str, str]
            ``(module_name, verilog)`` pair for the AND reduction map.
        """
        return self._render_template(
            REDUCE_AND_TECHMAP_TEMPLATE,
            {"reducer": self._context()},
        )

    def _context(self) -> dict[str, str]:
        """Build template values for ``$reduce_and``.

        Returns
        -------
        dict[str, str]
            Values controlling chain mode, seed, padding, inversion, and final
            result expression for the AND reduction template.
        """
        if self.config.and_to_or:
            return {
                "mode": "REDUCE_OR",
                "seed": "1'b0",
                "init_mode_id": "0",
                "pad_value": "1'b0",
                "source_bit_expr": "~data[offset + bit_idx]",
                "inv_in": "{CHUNK_SIZE{1'b1}}",
                "inv_out": "1'b1",
                "final_expr": "~chain[NUM_PRIMS]",
            }
        return {
            "mode": "REDUCE_AND",
            "seed": "1'b1",
            "init_mode_id": "1",
            "pad_value": "1'b1",
            "source_bit_expr": "data[offset + bit_idx]",
            "inv_in": "{CHUNK_SIZE{1'b0}}",
            "inv_out": "1'b0",
            "final_expr": "chain[NUM_PRIMS]",
        }


@dataclass(frozen=True)
class ReduceBoolTechmap(ChainCellTechmap):
    """Render the ``$reduce_bool`` chain techmap.

    Boolean reductions are treated as OR-style reductions by default because they test
    whether any input bit is high. When OR-to-AND conversion is enabled, the renderer
    emits the corresponding De Morgan context.
    """

    @property
    def module_name(self) -> str:
        """Return the generated techmap module name.

        Returns
        -------
        str
            Generated Verilog module name used by the ``techmap`` file.
        """
        return "_chain_reduce_bool"

    def render(self) -> tuple[str, str]:
        """Render the ``$reduce_bool`` techmap file.

        Returns
        -------
        tuple[str, str]
            ``(module_name, verilog)`` pair for the boolean reduction map.
        """
        return self._render_template(
            REDUCE_BOOL_TECHMAP_TEMPLATE,
            {"reducer": self._context()},
        )

    def _context(self) -> dict[str, str]:
        """Build template values for ``$reduce_bool``.

        Returns
        -------
        dict[str, str]
            Values controlling chain mode, seed, padding, inversion, and final
            result expression for the boolean reduction template.
        """
        if self.config.or_to_and:
            return {
                "mode": "REDUCE_AND",
                "seed": "1'b1",
                "init_mode_id": "1",
                "pad_value": "1'b1",
                "source_bit_expr": "~data[offset + bit_idx]",
                "inv_in": "{CHUNK_SIZE{1'b1}}",
                "inv_out": "1'b1",
                "final_expr": "~chain[NUM_PRIMS]",
            }
        return {
            "mode": "REDUCE_OR",
            "seed": "1'b0",
            "init_mode_id": "0",
            "pad_value": "1'b0",
            "source_bit_expr": "data[offset + bit_idx]",
            "inv_in": "{CHUNK_SIZE{1'b0}}",
            "inv_out": "1'b0",
            "final_expr": "chain[NUM_PRIMS]",
        }


@dataclass(frozen=True)
class ReduceOrTechmap(ChainCellTechmap):
    """Render the ``$reduce_or`` chain techmap.

    This renderer maps OR reductions directly to OR-mode chain primitives by default. If
    OR-to-AND conversion is enabled, it emits an AND-mode chain with inverted inputs and
    inverted final output.
    """

    @property
    def module_name(self) -> str:
        """Return the generated techmap module name.

        Returns
        -------
        str
            Generated Verilog module name used by the ``techmap`` file.
        """
        return "_chain_reduce_or"

    def render(self) -> tuple[str, str]:
        """Render the ``$reduce_or`` techmap file.

        Returns
        -------
        tuple[str, str]
            ``(module_name, verilog)`` pair for the OR reduction map.
        """
        return self._render_template(
            REDUCE_OR_TECHMAP_TEMPLATE,
            {"reducer": self._context()},
        )

    def _context(self) -> dict[str, str]:
        """Build template values for ``$reduce_or``.

        Returns
        -------
        dict[str, str]
            Values controlling chain mode, seed, padding, inversion, and final
            result expression for the OR reduction template.
        """
        if self.config.or_to_and:
            return {
                "mode": "REDUCE_AND",
                "seed": "1'b1",
                "init_mode_id": "1",
                "pad_value": "1'b1",
                "source_bit_expr": "~data[offset + bit_idx]",
                "inv_in": "{CHUNK_SIZE{1'b1}}",
                "inv_out": "1'b1",
                "final_expr": "~chain[NUM_PRIMS]",
            }
        return {
            "mode": "REDUCE_OR",
            "seed": "1'b0",
            "init_mode_id": "0",
            "pad_value": "1'b0",
            "source_bit_expr": "data[offset + bit_idx]",
            "inv_in": "{CHUNK_SIZE{1'b0}}",
            "inv_out": "1'b0",
            "final_expr": "chain[NUM_PRIMS]",
        }


@dataclass(frozen=True)
class ReduceXorTechmap(ChainCellTechmap):
    """Render the ``$reduce_xor`` chain techmap.

    XOR reductions are mapped directly to XOR-mode chain primitives. Tail chunks are
    padded with zero because zero is the neutral element for XOR.
    """

    @property
    def module_name(self) -> str:
        """Return the generated techmap module name.

        Returns
        -------
        str
            Generated Verilog module name used by the ``techmap`` file.
        """
        return "_chain_reduce_xor"

    def render(self) -> tuple[str, str]:
        """Render the ``$reduce_xor`` techmap file.

        Returns
        -------
        tuple[str, str]
            ``(module_name, verilog)`` pair for the XOR reduction map.
        """
        return self._render_template(
            REDUCE_XOR_TECHMAP_TEMPLATE,
            {"reducer": self._context()},
        )

    def _context(self) -> dict[str, str]:
        """Build template values for ``$reduce_xor``.

        Returns
        -------
        dict[str, str]
            Values controlling chain mode, seed, padding, inversion, and final
            result expression for the XOR reduction template.
        """
        return {
            "mode": "REDUCE_XOR",
            "seed": "1'b0",
            "init_mode_id": "2",
            "pad_value": "1'b0",
            "source_bit_expr": "data[offset + bit_idx]",
            "inv_in": "{CHUNK_SIZE{1'b0}}",
            "inv_out": "1'b0",
            "final_expr": "chain[NUM_PRIMS]",
        }


@dataclass(frozen=True)
class AluTechmap(ChainCellTechmap):
    """Render the ``$alu`` chain techmap.

    This renderer maps each normalized Yosys ``$alu`` bit to one chain
    primitive. The template performs signed/width normalization before emitting
    per-bit chain slices.
    """

    @property
    def module_name(self) -> str:
        """Return the generated techmap module name.

        Returns
        -------
        str
            Generated Verilog module name used by the ``techmap`` file.
        """
        return "_chain_alu"

    def render(self) -> tuple[str, str]:
        """Render the ``$alu`` techmap file.

        Returns
        -------
        tuple[str, str]
            ``(module_name, verilog)`` pair for the ALU map.
        """
        return self._render_template(
            ALU_TECHMAP_TEMPLATE,
            self._context(),
        )

    def _context(self) -> dict[str, str | int]:
        """Build template values for ``$alu``.

        Returns
        -------
        dict[str, str | int]
            Values controlling local INIT mode, local input width, and signal
            expressions for each emitted ALU chain slice.
        """
        full_adder_mode = self.config.alu_init_mode == AluInitMode.FULL_ADDER
        local_inputs = (
            "{carry[i], AA[i], BB[i]}" if full_adder_mode else "{AA[i], BB[i]}"
        )
        return {
            "alu_init_mode": self.config.alu_init_mode.value,
            "alu_n": 3 if full_adder_mode else 2,
            "alu_i_expr": local_inputs,
            "alu_a_expr": local_inputs,
            "alu_b_expr": local_inputs,
            "alu_init": "8'h96" if full_adder_mode else "4'h6",
        }
