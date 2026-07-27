"""Macro placement step that honours the FABulous macro placement mode.

Tile area optimisation resizes `DIE_AREA` on every iteration, but the `MACROS`
configuration carries absolute instance locations. Replaying those locations
unchanged pins each macro to the bottom-left corner as the die grows. The modes
here decide how a location is re-derived for the die actually in effect.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Self

import klayout.db as kdb
from librelane.config.variable import Macro, Orientation, Variable
from librelane.logging.logger import warn
from librelane.state.state import State
from librelane.steps import odb as Odb
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import MetricsUpdate, Step, StepException, ViewsUpdate

# LEF orientations that rotate the master by 90 degrees, transposing the
# footprint that the placement modes reason about.
_TRANSPOSING_ORIENTATIONS = frozenset(
    {Orientation.W, Orientation.E, Orientation.FW, Orientation.FE}
)


class MacroPlacementMode(StrEnum):
    """How a macro instance follows a `DIE_AREA` that optimisation rewrites."""

    FIX = "fix"
    RELATIVE = "relative"
    CENTRE = "centre"

    @classmethod
    def _missing_(cls, value: object) -> Self:
        """Look up a mode case-insensitively, accepting the `center` spelling.

        An unrecognised mode falls back to `fix`, which reproduces the behaviour
        of not setting the variable at all.
        """
        if isinstance(value, str):
            value_lower = value.lower()
            if value_lower == "center":
                return cls.CENTRE
            for member in cls:
                if member.value == value_lower:
                    return member

        valid = ", ".join(member.value for member in cls)
        warn(
            f"{value!r} is not a valid {cls.__name__} (valid: {valid}); falling "
            f"back to {cls.FIX.value}, which places every macro at its configured "
            "location."
        )
        return cls.FIX


@dataclass(frozen=True)
class MacroBox:
    """A placed macro footprint in micron, tagged with its instance name."""

    instance: str
    x: Decimal
    y: Decimal
    width: Decimal
    height: Decimal
    orientation: Orientation = Orientation.N


def read_macro_size(lef_files: list[Path], module: str) -> tuple[Decimal, Decimal]:
    """Read a macro's `SIZE` out of its LEF views.

    KLayout's LEF reader draws the declared `SIZE` onto a dedicated outline layer,
    so measuring that layer alone yields the size itself rather than the extent of
    the pins and obstructions drawn inside it.

    Parameters
    ----------
    lef_files : list[Path]
        LEF views of the macro, as carried by its `Macro` configuration entry.
    module : str
        Module name of the macro, which is also its LEF cell name.

    Returns
    -------
    tuple[Decimal, Decimal]
        The macro width and height, in micron.

    Raises
    ------
    ValueError
        If none of the LEF views declare the module.
    """
    layout = kdb.Layout()
    options = kdb.LoadLayoutOptions()
    for lef_file in lef_files:
        layout.read(str(lef_file), options)

    # The reader names the outline layer but also numbers it, so it has to be
    # looked up by name; building a LayerInfo from the name alone would create a
    # fresh empty layer instead of matching the one that was read.
    outline_name = options.lefdef_config.cell_outline_layer
    outline_layers = [
        index
        for index in layout.layer_indexes()
        if layout.get_info(index).name == outline_name
    ]

    cell = layout.cell(module)
    outline = kdb.Box()
    if cell is not None:
        for index in outline_layers:
            outline += cell.bbox_per_layer(index)

    if outline.empty():
        raise ValueError(
            f"No outline for macro {module} in its LEF views "
            f"({', '.join(str(f) for f in lef_files)}). Check that the module name "
            "matches the MACRO declared in the LEF."
        )

    dbu = Decimal(str(layout.dbu))

    return Decimal(outline.width()) * dbu, Decimal(outline.height()) * dbu


def oriented_footprint(
    macro_size: tuple[Decimal, Decimal], orientation: Orientation
) -> tuple[Decimal, Decimal]:
    """Return the footprint a macro occupies once placed at `orientation`.

    Parameters
    ----------
    macro_size : tuple[Decimal, Decimal]
        Unrotated macro width and height, in micron.
    orientation : Orientation
        LEF orientation the instance is placed at.

    Returns
    -------
    tuple[Decimal, Decimal]
        Width and height of the placed footprint, in micron.
    """
    if orientation in _TRANSPOSING_ORIENTATIONS:
        return macro_size[1], macro_size[0]

    return macro_size


def relocate_macro(
    instance: str,
    mode: MacroPlacementMode,
    location: tuple[Decimal, Decimal],
    macro_size: tuple[Decimal, Decimal],
    live_die: tuple[Decimal, Decimal],
    reference_die: tuple[Decimal, Decimal] | None,
) -> tuple[Decimal, Decimal]:
    """Re-derive a macro's origin for the die area currently in effect.

    Parameters
    ----------
    instance : str
        Instance name, used to make the raised errors actionable.
    mode : MacroPlacementMode
        Placement mode governing how the location is derived.
    location : tuple[Decimal, Decimal]
        Configured origin of the macro, in micron.
    macro_size : tuple[Decimal, Decimal]
        Macro width and height taken from its LEF, in micron.
    live_die : tuple[Decimal, Decimal]
        Width and height of the die area currently in effect, in micron. Die
        areas in this flow always start at the origin, so extents suffice.
    reference_die : tuple[Decimal, Decimal] | None
        Width and height of the die area `location` was authored against.
        Required by `relative` and unused by the other modes.

    Returns
    -------
    tuple[Decimal, Decimal]
        The origin the macro should be placed at, in micron.

    Raises
    ------
    ValueError
        If the macro does not fit in `live_die`, if `relative` is requested
        without a `reference_die`, or if the configured location leaves no free
        margin to distribute the die growth across.
    """
    for axis, macro_extent, live_extent in (
        ("width", macro_size[0], live_die[0]),
        ("height", macro_size[1], live_die[1]),
    ):
        if macro_extent > live_extent:
            raise ValueError(
                f"Macro instance {instance} does not fit the die: macro {axis} "
                f"{macro_extent} exceeds die {axis} {live_extent}."
            )

    match mode:
        case MacroPlacementMode.FIX:
            return location
        case MacroPlacementMode.CENTRE:
            return (
                (live_die[0] - macro_size[0]) / 2,
                (live_die[1] - macro_size[1]) / 2,
            )
        case MacroPlacementMode.RELATIVE:
            if reference_die is None:
                raise ValueError(
                    f"Macro instance {instance} uses the relative placement mode, "
                    "which needs a reference die area to measure the original "
                    "margins against."
                )
            origin = []
            for axis, axis_location, macro_extent, live_extent, reference_extent in (
                ("width", location[0], macro_size[0], live_die[0], reference_die[0]),
                ("height", location[1], macro_size[1], live_die[1], reference_die[1]),
            ):
                low = axis_location
                high = reference_extent - axis_location - macro_extent
                if low < 0 or high < 0:
                    raise ValueError(
                        f"Macro instance {instance} sits outside the reference die "
                        f"on the {axis} axis: origin {axis_location} plus {axis} "
                        f"{macro_extent} against a reference {axis} of "
                        f"{reference_extent}."
                    )
                if low + high == 0:
                    raise ValueError(
                        f"Macro instance {instance} fills the reference die {axis} "
                        "exactly, leaving no free margin to distribute the die "
                        "growth across. Use the fix or centre placement mode "
                        "instead."
                    )
                # Splitting the change in proportion to the original margins keeps a
                # centred macro centred and an edge-hugging one at its edge.
                origin.append(
                    axis_location
                    + (live_extent - reference_extent) * low / (low + high)
                )
            return origin[0], origin[1]
        case _:
            raise ValueError(f"Unknown macro placement mode: {mode}")


def find_overlapping_pair(boxes: list[MacroBox]) -> tuple[MacroBox, MacroBox] | None:
    """Return the first pair of macro footprints that share area.

    Abutting macros share an edge but no area and are therefore legal.

    Parameters
    ----------
    boxes : list[MacroBox]
        Macro footprints to check against each other.

    Returns
    -------
    tuple[MacroBox, MacroBox] | None
        The first overlapping pair found, or None when the placement is legal.
    """
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            overlaps_x = (
                first.x < second.x + second.width and second.x < first.x + first.width
            )
            overlaps_y = (
                first.y < second.y + second.height and second.y < first.y + first.height
            )
            if overlaps_x and overlaps_y:
                return first, second

    return None


var = [
    Variable(
        "FABULOUS_MACRO_PLACEMENT_MODE",
        str,
        "How macro instances follow a `DIE_AREA` that tile optimisation rewrites "
        "on every iteration. Options are: "
        " - 'fix': default, place every macro at its configured location. "
        " - 'relative': split the die area change across each macro's free "
        "margins, so a centred macro stays centred and one placed against an "
        "edge stays against it. Needs a `DIE_AREA` to measure the original "
        "margins against. "
        " - 'centre': ignore the configured location and centre the macro in the "
        "die. Only meaningful for a tile holding a single macro instance.",
        default=MacroPlacementMode.FIX.value,
    ),
    Variable(
        "FABULOUS_MACRO_REFERENCE_DIE_AREA",
        tuple[Decimal, Decimal, Decimal, Decimal] | None,
        "The die area the `MACROS` locations were authored against, captured by "
        "the tile flow before optimisation starts rewriting `DIE_AREA`. Read by "
        "the 'relative' placement mode; not meant to be set by hand.",
        default=None,
        units="µm",
    ),
]


@Step.factory.register()
class FABulousMacroPlacement(Odb.ManualMacroPlacement):
    """Place macros at locations derived from the macro placement mode.

    Only the placement config is FABulous-specific: the locations are re-derived
    for the die area currently in effect and then handed to librelane's own macro
    placer, which does the placing.
    """

    id = "FABulousMacroPlacement"
    name = "FABulous Macro Placement"

    config_vars = Odb.ManualMacroPlacement.config_vars + var

    def run(self, state_in: State, **kwargs: dict) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Emit the placement config and run librelane's macro placer.

        Parameters
        ----------
        state_in : State
            The state entering the step.
        **kwargs : dict
            Extra arguments forwarded to the underlying odbpy step.

        Returns
        -------
        tuple[ViewsUpdate, MetricsUpdate]
            The view and metric updates produced by the step.

        Raises
        ------
        StepException
            If a `MACROS` entry is not a `Macro` object, if `relative` lacks a
            location or a reference die area, or if the derived placement makes
            two macros overlap.
        """
        mode = MacroPlacementMode(self.config["FABULOUS_MACRO_PLACEMENT_MODE"])
        macros = self.config.get("MACROS")
        # `fix` replays the configured locations, which is exactly what librelane's
        # own config writer emits, and an explicit cfg overrides `MACROS` entirely.
        if (
            mode == MacroPlacementMode.FIX
            or self.config.get("MACRO_PLACEMENT_CFG") is not None
            or not macros
        ):
            return super().run(state_in, **kwargs)

        _, _, die_width, die_height = self.config["DIE_AREA"]
        reference = self.config["FABULOUS_MACRO_REFERENCE_DIE_AREA"]
        if mode == MacroPlacementMode.RELATIVE and reference is None:
            raise StepException(
                "The relative macro placement mode needs a reference die area to "
                "measure the original macro margins against. Set DIE_AREA with "
                "FABULOUS_IGNORE_DEFAULT_DIE_AREA false, or use the centre mode."
            )

        boxes = self._place_macros(mode, macros, (die_width, die_height), reference)
        if pair := find_overlapping_pair(boxes):
            first, second = pair
            raise StepException(
                f"Macro instances {first.instance} and {second.instance} overlap "
                f"after {mode.value} placement: {first} against {second}. Place "
                "them with the fix mode, or give them locations that stay disjoint "
                "as the die area changes."
            )

        (Path(self.step_dir) / "placement.cfg").write_text(
            "".join(f"{b.instance} {b.x} {b.y} {b.orientation}\n" for b in boxes)
        )

        return OdbpyStep.run(self, state_in, **kwargs)

    def _place_macros(
        self,
        mode: MacroPlacementMode,
        macros: dict[str, Macro],
        live_die: tuple[Decimal, Decimal],
        reference: tuple[Decimal, Decimal, Decimal, Decimal] | None,
    ) -> list[MacroBox]:
        """Derive every macro instance's footprint for the live die area.

        Parameters
        ----------
        mode : MacroPlacementMode
            Placement mode governing how each location is derived.
        macros : dict[str, Macro]
            The `MACROS` configuration, keyed by module name.
        live_die : tuple[Decimal, Decimal]
            Width and height of the die area currently in effect, in micron.
        reference : tuple[Decimal, Decimal, Decimal, Decimal] | None
            The reference die area, needed by `relative`.

        Returns
        -------
        list[MacroBox]
            One placed footprint per macro instance.

        Raises
        ------
        StepException
            If an entry is not a `Macro`, or if `relative` meets an instance with
            no configured location to measure margins from.
        """
        reference_die = (reference[2], reference[3]) if reference else None

        boxes = []
        for module, macro in macros.items():
            if not isinstance(macro, Macro):
                raise StepException(
                    "Misconstructed configuration: macro definition for key "
                    f"{module} is not of type 'Macro'."
                )

            macro_size = read_macro_size(macro.lef, module)
            for name, instance in macro.instances.items():
                if mode == MacroPlacementMode.RELATIVE and instance.location is None:
                    raise StepException(
                        f"Instance {name} of macro {module} has no location, so the "
                        "relative placement mode has no margins to preserve. Give "
                        "it a location, or use the centre mode."
                    )

                orientation = instance.orientation or Orientation.N
                footprint = oriented_footprint(macro_size, orientation)
                x, y = relocate_macro(
                    name,
                    mode,
                    instance.location or (Decimal(0), Decimal(0)),
                    footprint,
                    live_die,
                    reference_die,
                )
                boxes.append(MacroBox(name, x, y, *footprint, orientation))

        return boxes
