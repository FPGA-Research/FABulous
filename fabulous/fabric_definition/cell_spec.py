"""Standard-cell specifications for timing characterization.

A standard-cell library ({class}`StdCellLibrary`) bundles everything the timing
flow needs for one PDK: the liberty timing files, the Yosys techmap files, and
the standard cells the synthesizer maps onto, grouped by the logical function
they fill ({class}`CellFunction`). Each cell is a {class}`CellSpec` -- its name
plus the ports a cell-mapping tool needs, with room to grow more metadata.

The library is parsed (and validated) from one `pdk::<variant>` section of the
project's `Fabric/std_cell_library.yaml` via {meth}`StdCellLibrary.load`, so a
PDK is characterized -- or repointed -- by editing that file instead of changing
code. Liberty/techmap paths may be absolute, relative to the project directory,
or reference `${VAR}` placeholders (e.g. `${PDK_ROOT}`, `${PDK}`) that the
caller resolves from the active settings. Add a section to characterize another
PDK, and add a member to {class}`CellFunction` (with a matching `cells` key) to
teach it a new cell type.
"""

import re
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, RootModel, ValidationInfo, field_validator

STD_CELL_LIBRARY_RELPATH = Path("Fabric") / "std_cell_library.yaml"
"""Project-relative path to the per-PDK standard-cell library file."""

_VARIABLE_PATTERN = re.compile(r"\$\{(\w+)\}")


def _expand_variables(raw: str, variables: dict[str, str]) -> str:
    """Substitute `${VAR}` placeholders in `raw` with `variables` values.

    Parameters
    ----------
    raw : str
        The string to expand, possibly containing `${VAR}` placeholders.
    variables : dict[str, str]
        Placeholder name to value mapping (e.g. `{"PDK_ROOT": "/pdks"}`).

    Returns
    -------
    str
        `raw` with every placeholder replaced by its value.

    Raises
    ------
    ValueError
        If `raw` references a placeholder not present in `variables`.
    """
    for name in _VARIABLE_PATTERN.findall(raw):
        if name not in variables:
            available = ", ".join(sorted(variables)) or "none"
            raise ValueError(
                f"Unknown variable '${{{name}}}' in path {raw!r}. "
                f"Available variables: {available}."
            )
    return _VARIABLE_PATTERN.sub(lambda match: variables[match.group(1)], raw)


class CellFunction(StrEnum):
    """The logical role a standard cell fills during timing characterization.

    The members are the keys of a library's `cells` mapping and the argument
    to {meth}`StdCellLibrary.get`; they are the extension point for new cell
    types.
    """

    BUFFER = "buffer"
    TIE_HIGH = "tie_high"
    TIE_LOW = "tie_low"
    LATCH = "latch"
    MUX = "mux"


class CellSpec(BaseModel):
    """A standard cell and the ports a cell-mapping tool needs to use it.

    `cell` is the standard-cell name; `input_ports` and `output_ports` list
    its ports (a buffer has one of each, a tie cell only an output, and cells
    with several inputs/outputs list them all). Add further fields -- drive
    strength, area, ... -- as more cell metadata is needed.
    """

    model_config = ConfigDict(frozen=True)

    cell: str
    input_ports: tuple[str, ...] = ()
    output_ports: tuple[str, ...] = ()

    @property
    def yosys_arg(self) -> str:
        """Render the cell and its ports as a Yosys cell-mapping argument.

        Returns
        -------
        str
            The cell followed by its input ports then output ports, as Yosys
            options such as `insbuf -buf` and `hilomap` expect: a buffer
            renders `"buf_1 A X"`, a tie cell `"conb_1 HI"`.
        """
        return " ".join((self.cell, *self.input_ports, *self.output_ports))


class StdCellLibrary(BaseModel):
    """A PDK's standard-cell library for timing characterization.

    Bundles the liberty timing files and Yosys techmap files with the cells the
    synthesizer maps onto, grouped by function. A function may map to several
    cells (e.g. multiple buffers); use {meth}`get` to fetch them. Liberty and
    techmap entries accept `${VAR}` placeholders and relative paths, resolved
    against the validation context supplied by {meth}`load`.
    """

    liberty_files: list[Path] = []
    techmap_files: list[Path] = []
    cells: dict[CellFunction, list[CellSpec]] = {}

    @field_validator("liberty_files", "techmap_files", mode="before")
    @classmethod
    def _resolve_path_list(cls, value: object, info: ValidationInfo) -> object:
        """Expand `${VAR}` placeholders and resolve relative path entries.

        Placeholder values and the base directory for relative entries come from
        the validation context (`variables` and `base_dir`); absolute paths
        are left untouched.

        Parameters
        ----------
        value : object
            The raw field value: a path string or a list of path strings.
        info : ValidationInfo
            Validation context carrying `variables` and `base_dir`.

        Returns
        -------
        object
            The list of resolved paths.
        """
        if value is None:
            return []
        if isinstance(value, (str, Path)):
            value = [value]

        context = info.context or {}
        variables: dict[str, str] = context.get("variables", {})
        base_dir = context.get("base_dir")

        resolved: list[Path] = []
        for entry in value:
            path = Path(_expand_variables(str(entry), variables)).expanduser()
            if not path.is_absolute() and base_dir is not None:
                path = Path(base_dir) / path
            resolved.append(path)
        return resolved

    def get(self, function: CellFunction) -> list[CellSpec]:
        """Return the cells declared for `function`.

        Parameters
        ----------
        function : CellFunction
            The logical role to look up.

        Returns
        -------
        list[CellSpec]
            The cells declared for `function` in declaration order, empty when
            the library declares none.
        """
        return self.cells.get(function, [])

    @classmethod
    def load(
        cls, project_dir: Path, pdk: str, variables: dict[str, str] | None = None
    ) -> Self:
        """Load the standard-cell library for `pdk` from the project file.

        Parameters
        ----------
        project_dir : Path
            Project directory containing `Fabric/std_cell_library.yaml`.
        pdk : str
            Active PDK variant name, matched against a `pdk::<name>` section.
        variables : dict[str, str] | None
            Placeholder values for `${VAR}` references in liberty/techmap
            paths (e.g. `{"PDK_ROOT": ..., "PDK": ...}`); None for no
            placeholders.

        Returns
        -------
        Self
            The standard-cell library for the PDK.

        Raises
        ------
        FileNotFoundError
            If the standard-cell library file does not exist.
        ValueError
            If the file has no section for `pdk` or the section is malformed.
        """
        config_path = project_dir / STD_CELL_LIBRARY_RELPATH
        if not config_path.exists():
            raise FileNotFoundError(
                f"Standard-cell library file not found at {config_path}. It ships "
                "with the project template; add one to characterize timing."
            )

        data = yaml.safe_load(config_path.read_text()) or {}
        section = data.get(f"pdk::{pdk}")
        if section is None:
            raise ValueError(
                f"No 'pdk::{pdk}' section in {config_path}. "
                "Add a section for this PDK to characterize its timing."
            )
        resolved_vars = {"PROJ_DIR": str(project_dir), **(variables or {})}
        return cls.model_validate(
            section,
            context={"variables": resolved_vars, "base_dir": project_dir},
        )


class StdCellLibraryFile(RootModel[dict[str, StdCellLibrary]]):
    """The on-disk standard-cell library config: `pdk::<variant>` sections.

    Maps each `pdk::<variant>` section name to its {class}`StdCellLibrary`.
    Used to emit the JSON schema for `Fabric/std_cell_library.yaml`.
    """
