"""Build FABulous tile files from BEL RTL and routing options.

The builder is the orchestration layer for the tile-builder module. It delegates BEL
metadata extraction and HDL generation to FABulous where possible, writes only the tile-
level CSV/list files that fabxplore owns, and returns a structured report for the PnR
pass wrapper.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.base_model import (
    BaseRoutingModel,
    build_base_routing_model,
)
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    BaselineListResult,
    FabulousCsvKeyword,
    FabulousSpecialFeature,
    TileBel,
    TileBuilderArtifact,
    TileBuilderGeneratedWire,
    TileBuilderOptions,
    TileBuilderResult,
    TileBuilderStats,
)
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.process_tracker import (
    TileBuilderProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.report import (
    render_tile_builder_report,
)
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.gen_fabric.fabric_automation import addBelsToPrim
from fabulous.fabric_generator.parser.parse_hdl import parseBelFile
from fabulous.fabulous_settings import get_context

from . import baseline_list_generator

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge
    from fabulous.fabric_definition.bel import Bel
    from fabulous.fabulous_api import FABulous_API


class TileBuilder:
    """Generate a FABulous tile package from typed options.

    Parameters
    ----------
    options : TileBuilderOptions
        Normalized builder options.
    """

    def __init__(self, options: TileBuilderOptions) -> None:
        self.options = options

    def build(self, fpga_model: PnRBridge) -> TileBuilderResult:
        """Build the tile package in the active FABulous project.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and routing graph.
            The current builder records the design dependency but does not
            mutate the design.

        Returns
        -------
        TileBuilderResult
            Structured result and report.
        """
        design = fpga_model.user_design
        fab = fpga_model.fab
        _ = design
        project_dir = _project_dir(fab)
        fabric_csv = project_dir / "fabric.csv"
        tile_dir = (
            self.options.tile_dir or project_dir / "Tile" / self.options.tile_name
        )
        tile_dir.mkdir(parents=True, exist_ok=True)
        _remove_legacy_matrix_artifacts(tile_dir, self.options.tile_name)

        tracker = TileBuilderProcessTracker(
            enabled=self.options.track_progress,
            chunk_size=self.options.progress_chunk_size,
        )
        tracker.start(self.options.tile_name, _bel_instance_count(self.options.bels))

        copied_sources = _copy_bel_sources(self.options.bels, tile_dir)
        parsed_bels, custom_prim_bels = _parse_bels(copied_sources, tracker)
        artifacts = [
            TileBuilderArtifact(kind="bel_rtl", path=path)
            for path in sorted({path for path, _prefix, _custom in copied_sources})
        ]

        baseline_result: BaselineListResult | None = None
        matrix_list: Path | None = None
        warnings: list[str] = []
        capacity = _config_capacity(fab, self.options.config_bit_capacity_override)
        bel_config_bits = sum(bel.configBit for bel in parsed_bels)
        matrix_budget = (
            capacity - bel_config_bits - self.options.routing.config_bit_margin
        )
        base_model = build_base_routing_model(
            tile_dir=tile_dir,
            routing=self.options.routing,
            require_gnd=_needs_shared_kind(parsed_bels, FabulousSpecialFeature.RESET),
            require_vcc=_needs_shared_kind(parsed_bels, FabulousSpecialFeature.ENABLE),
        )

        if self.options.routing.use_fabulous_auto:
            matrix_line = ",".join(
                [FabulousCsvKeyword.MATRIX, FabulousCsvKeyword.GENERATE]
            )
        else:
            matrix_list = tile_dir / f"{self.options.tile_name}_switch_matrix.list"
            baseline_result = baseline_list_generator.generate_baseline_list(
                tile_name=self.options.tile_name,
                bels=parsed_bels,
                routing=self.options.routing,
                base_model=base_model,
                matrix_config_budget=matrix_budget,
            )
            matrix_list.write_text(baseline_result.text, encoding="utf-8")
            tracker.wrote_file("switch matrix list", matrix_list)
            artifacts.append(TileBuilderArtifact(kind="matrix_list", path=matrix_list))
            warnings.extend(baseline_result.warnings)
            matrix_line = f"MATRIX,./{matrix_list.name}"

        tile_csv = tile_dir / f"{self.options.tile_name}.csv"
        _write_tile_csv(
            tile_csv=tile_csv,
            tile_name=self.options.tile_name,
            bel_specs=self.options.bels,
            copied_sources=copied_sources,
            parsed_bels=parsed_bels,
            matrix_line=matrix_line,
            base_model=base_model,
            generated_csv_lines=baseline_result.generated_csv_lines
            if baseline_result
            else (),
        )
        tracker.wrote_file("tile csv", tile_csv)
        artifacts.append(TileBuilderArtifact(kind="tile_csv", path=tile_csv))

        if custom_prim_bels:
            prims_file = project_dir / "user_design" / "custom_prims.v"
            prims_file.parent.mkdir(parents=True, exist_ok=True)
            addBelsToPrim(prims_file, custom_prim_bels)
            artifacts.append(TileBuilderArtifact(kind="custom_prims", path=prims_file))
            tracker.wrote_file("custom primitives", prims_file)

        if self.options.register_in_fabric:
            _register_tile_in_fabric(fabric_csv, project_dir, tile_csv)
            artifacts.append(TileBuilderArtifact(kind="fabric_csv", path=fabric_csv))

        fab.loadFabric(fabric_csv)
        tile = fab.fabric.getTileByName(self.options.tile_name)
        _check_config_capacity(
            tile_name=self.options.tile_name,
            used_bits=tile.globalConfigBits,
            capacity=capacity,
            margin=self.options.routing.config_bit_margin,
        )

        generated_artifacts = _run_fabulous_generation(
            fab=fab,
            tile_name=self.options.tile_name,
            tile_dir=tile_dir,
            file_extension=fab.fileExtension,
        )
        artifacts.extend(generated_artifacts)
        for artifact in generated_artifacts:
            tracker.wrote_file(artifact.kind, artifact.path)

        command_file = tile_dir / "command.txt"
        _write_command_file(command_file, self.options.tile_name, tile_dir)
        artifacts.append(TileBuilderArtifact(kind="commands", path=command_file))

        stats = TileBuilderStats(
            bel_instances=len(parsed_bels),
            unique_bel_modules=len({bel.module_name for bel in parsed_bels}),
            bel_config_bits=bel_config_bits,
            matrix_config_bits=tile.matrixConfigBits,
            total_config_bits=tile.globalConfigBits,
            config_capacity=capacity,
            input_muxes=baseline_result.input_muxes if baseline_result else 0,
            output_muxes=baseline_result.output_muxes if baseline_result else 0,
            direct_connections=baseline_result.direct_connections
            if baseline_result
            else 0,
            input_fanin_used=baseline_result.input_fanin_used if baseline_result else 0,
            output_fanin_used=baseline_result.output_fanin_used
            if baseline_result
            else 0,
            routing_pattern_pips=baseline_result.routing_pattern_pips
            if baseline_result
            else 0,
            routing_pattern_groups=baseline_result.routing_pattern_groups
            if baseline_result
            else 0,
            routing_pip_fs_used=baseline_result.routing_pip_fs_used
            if baseline_result
            else 0,
            connection_hierarchy_enabled=baseline_result.connection_hierarchy_enabled
            if baseline_result
            else False,
            connection_hierarchy_levels=baseline_result.connection_hierarchy_levels
            if baseline_result
            else (),
            active_connection_hierarchy_levels=(
                baseline_result.active_connection_hierarchy_levels
                if baseline_result
                else ()
            ),
            generated_jump_wires=baseline_result.generated_jump_wires
            if baseline_result
            else 0,
            hierarchy_source_pips=baseline_result.hierarchy_source_pips
            if baseline_result
            else 0,
            hierarchy_sink_pips=baseline_result.hierarchy_sink_pips
            if baseline_result
            else 0,
            bypassed_hierarchy_inputs=baseline_result.bypassed_hierarchy_inputs
            if baseline_result
            else 0,
        )

        result = TileBuilderResult(
            options=self.options.model_copy(update={"tile_dir": tile_dir}),
            tile_name=self.options.tile_name,
            tile_dir=tile_dir,
            tile_csv=tile_csv,
            matrix_list=matrix_list,
            parsed_bel_modules=tuple(bel.module_name for bel in parsed_bels),
            artifacts=tuple(artifacts),
            stats=stats,
            warnings=tuple(warnings),
        )
        result = result.model_copy(
            update={"report_summary": render_tile_builder_report(result)}
        )
        tracker.finish(self.options.tile_name, stats.total_config_bits, capacity)
        return result


def _project_dir(fab: FABulous_API) -> Path:
    """Return the active project directory.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.

    Returns
    -------
    Path
        Project directory.
    """
    fabric = getattr(fab, "fabric", None)
    fabric_dir = getattr(fabric, "fabric_dir", None)
    if fabric_dir is not None:
        return Path(fabric_dir).resolve().parent
    return get_context().proj_dir


def _bel_instance_count(bels: list[TileBel]) -> int:
    """Count BEL instances described by the options.

    Parameters
    ----------
    bels : list[TileBel]
        BEL specifications.

    Returns
    -------
    int
        Number of BEL instances.
    """
    return sum(len(bel.prefixes) for bel in bels)


def _copy_bel_sources(
    bels: list[TileBel], tile_dir: Path
) -> list[tuple[Path, str, bool]]:
    """Copy BEL RTL files into the generated tile directory.

    Parameters
    ----------
    bels : list[TileBel]
        BEL specifications.
    tile_dir : Path
        Destination tile directory.

    Returns
    -------
    list[tuple[Path, str, bool]]
        Copied path, prefix, and custom-primitive flag per BEL instance.

    Raises
    ------
    FileNotFoundError
        If a BEL RTL file does not exist.
    ValueError
        If two different BEL sources share the same file name.
    """
    copied_by_name: dict[str, Path] = {}
    records: list[tuple[Path, str, bool]] = []
    for bel in bels:
        source = bel.verilog_path.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"BEL RTL file does not exist: {source}")
        destination = tile_dir / source.name
        existing_source = copied_by_name.get(source.name)
        if existing_source is not None and existing_source != source:
            raise ValueError(
                f"BEL RTL filename collision for {source.name}: "
                f"{existing_source} and {source}"
            )
        copied_by_name[source.name] = source
        if source != destination.resolve():
            shutil.copy2(source, destination)
        for prefix in bel.prefixes:
            records.append((destination, prefix, bel.add_as_custom_prim))
    return records


def _parse_bels(
    copied_sources: list[tuple[Path, str, bool]],
    tracker: TileBuilderProcessTracker,
) -> tuple[list[Bel], list[Bel]]:
    """Parse copied BEL RTL files through FABulous.

    Parameters
    ----------
    copied_sources : list[tuple[Path, str, bool]]
        Copied path, prefix, and custom-primitive flag per BEL instance.
    tracker : TileBuilderProcessTracker
        Progress tracker.

    Returns
    -------
    tuple[list[Bel], list[Bel]]
        All parsed BEL instances and the subset to add as custom primitives.
    """
    parsed: list[Bel] = []
    custom_prims: list[Bel] = []
    for path, prefix, add_custom_prim in copied_sources:
        bel = parseBelFile(path, prefix)
        parsed.append(bel)
        if add_custom_prim:
            custom_prims.append(bel)
        tracker.record_bel()
    return parsed, custom_prims


def _write_tile_csv(
    tile_csv: Path,
    tile_name: str,
    bel_specs: list[TileBel],
    copied_sources: list[tuple[Path, str, bool]],
    parsed_bels: list[Bel],
    matrix_line: str,
    base_model: BaseRoutingModel,
    generated_csv_lines: tuple[str, ...],
) -> None:
    """Write the FABulous tile CSV.

    Parameters
    ----------
    tile_csv : Path
        Tile CSV path.
    tile_name : str
        Tile name.
    bel_specs : list[TileBel]
        Original BEL specifications.
    copied_sources : list[tuple[Path, str, bool]]
        Copied path, prefix, and custom-primitive flag per BEL instance.
    parsed_bels : list[Bel]
        Parsed BEL instances.
    matrix_line : str
        Matrix line to emit.
    base_model : BaseRoutingModel
        Discovered base routing resources.
    generated_csv_lines : tuple[str, ...]
        Additional tile CSV wire rows generated by baseline list generation.
    """
    _ = bel_specs
    lines = [f"{FabulousCsvKeyword.TILE},{tile_name}"]
    lines.extend(
        f"{FabulousCsvKeyword.INCLUDE},{include}" for include in base_model.csv_includes
    )
    lines.extend(base_model.extra_csv_lines)
    lines.extend(generated_csv_lines)
    lines.extend(_carry_csv_lines(parsed_bels))
    lines.extend(_local_shared_csv_lines(parsed_bels))
    for path, prefix, _custom in copied_sources:
        lines.append(f"{FabulousCsvKeyword.BEL},./{path.name},{prefix}")
    lines.append(matrix_line)
    lines.append(FabulousCsvKeyword.END_TILE)
    tile_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _carry_csv_lines(parsed_bels: list[Bel]) -> list[str]:
    """Return tile CSV carry boundary lines.

    Parameters
    ----------
    parsed_bels : list[Bel]
        Parsed BEL instances.

    Returns
    -------
    list[str]
        CSV lines for tile carry boundaries.
    """
    carry_names = sorted({name for bel in parsed_bels for name in bel.carry})
    return [
        (
            f"{Direction.NORTH.value},"
            f"{TileBuilderGeneratedWire.CARRY_OUT}{index},"
            "0,-1,"
            f"{TileBuilderGeneratedWire.CARRY_IN}{index},"
            f'1,{FabulousSpecialFeature.CARRY}="{carry_name}"'
        )
        for index, carry_name in enumerate(carry_names)
    ]


def _local_shared_csv_lines(parsed_bels: list[Bel]) -> list[str]:
    """Return tile CSV local shared jump lines.

    Parameters
    ----------
    parsed_bels : list[Bel]
        Parsed BEL instances.

    Returns
    -------
    list[str]
        CSV lines for local shared reset and enable jumps.
    """
    shared_kinds = {kind for bel in parsed_bels for kind in bel.localShared}
    lines: list[str] = []
    if FabulousSpecialFeature.RESET in shared_kinds:
        lines.append(
            ",".join(
                [
                    Direction.JUMP.value,
                    TileBuilderGeneratedWire.RESET_BEGIN,
                    "0",
                    "0",
                    TileBuilderGeneratedWire.RESET_END,
                    "1",
                    FabulousSpecialFeature.SHARED_RESET,
                ]
            )
        )
    if FabulousSpecialFeature.ENABLE in shared_kinds:
        lines.append(
            ",".join(
                [
                    Direction.JUMP.value,
                    TileBuilderGeneratedWire.ENABLE_BEGIN,
                    "0",
                    "0",
                    TileBuilderGeneratedWire.ENABLE_END,
                    "1",
                    FabulousSpecialFeature.SHARED_ENABLE,
                ]
            )
        )
    return lines


def _needs_shared_kind(parsed_bels: list[Bel], shared_kind: str) -> bool:
    """Return whether parsed BELs use one local shared kind.

    Parameters
    ----------
    parsed_bels : list[Bel]
        Parsed BEL instances.
    shared_kind : str
        Local shared kind, such as ``RESET`` or ``ENABLE``.

    Returns
    -------
    bool
        Whether any BEL uses the shared kind.
    """
    return any(shared_kind in bel.localShared for bel in parsed_bels)


def _register_tile_in_fabric(
    fabric_csv: Path,
    project_dir: Path,
    tile_csv: Path,
) -> None:
    """Ensure the generated tile CSV is listed in ``fabric.csv``.

    Parameters
    ----------
    fabric_csv : Path
        Project fabric CSV path.
    project_dir : Path
        Project directory.
    tile_csv : Path
        Tile CSV path to register.

    Raises
    ------
    FileNotFoundError
        If ``fabric.csv`` does not exist.
    ValueError
        If ``ParametersEnd`` cannot be found.
    """
    if not fabric_csv.is_file():
        raise FileNotFoundError(f"fabric.csv does not exist: {fabric_csv}")
    rel_tile_csv = tile_csv.relative_to(project_dir).as_posix()
    tile_line = f"{FabulousCsvKeyword.FABRIC_TILE_ENTRY},./{rel_tile_csv}"
    text = fabric_csv.read_text(encoding="utf-8")
    if tile_line in text or f"Tile,{rel_tile_csv}" in text:
        return
    marker = FabulousCsvKeyword.PARAMETERS_END
    if marker not in text:
        raise ValueError(f"Cannot find {marker} in {fabric_csv}")
    text = text.replace(marker, f"{tile_line}\n{marker}", 1)
    fabric_csv.write_text(text, encoding="utf-8")


def _config_capacity(fab: FABulous_API, override: int | None = None) -> int:
    """Return the fabric config-bit capacity for one tile.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.
    override : int | None
        Optional capacity override.

    Returns
    -------
    int
        Frame bits per row multiplied by maximum frames per column.
    """
    if override is not None:
        return override
    return fab.fabric.frameBitsPerRow * fab.fabric.maxFramesPerCol


def _check_config_capacity(
    tile_name: str,
    used_bits: int,
    capacity: int,
    margin: int,
) -> None:
    """Validate that the generated tile fits the config-bit capacity.

    Parameters
    ----------
    tile_name : str
        Generated tile name.
    used_bits : int
        Total generated config bits.
    capacity : int
        Fabric config-bit capacity.
    margin : int
        Required unused margin.

    Raises
    ------
    RuntimeError
        If the generated tile exceeds the usable capacity.
    """
    usable = capacity - margin
    if used_bits > usable:
        raise RuntimeError(
            f"Tile {tile_name} uses {used_bits} config bits, but only {usable} "
            f"of {capacity} are usable with margin {margin}."
        )


def _run_fabulous_generation(
    fab: FABulous_API,
    tile_name: str,
    tile_dir: Path,
    file_extension: str,
) -> list[TileBuilderArtifact]:
    """Run FABulous generators for one tile.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.
    tile_name : str
        Tile to generate.
    tile_dir : Path
        Tile directory.
    file_extension : str
        FABulous HDL file extension.

    Returns
    -------
    list[TileBuilderArtifact]
        Generated artifact records.
    """
    switch_matrix = tile_dir / f"{tile_name}_switch_matrix{file_extension}"
    config_mem = tile_dir / f"{tile_name}_ConfigMem{file_extension}"
    config_mem_csv = tile_dir / f"{tile_name}_ConfigMem.csv"
    tile_rtl = tile_dir / f"{tile_name}{file_extension}"

    fab.setWriterOutputFile(switch_matrix)
    fab.genSwitchMatrix(tile_name)
    _remove_stale_config_mem_csv(config_mem_csv)
    fab.setWriterOutputFile(config_mem)
    fab.genConfigMem(tile_name, config_mem_csv)
    fab.setWriterOutputFile(tile_rtl)
    fab.genTile(tile_name)

    artifacts = [
        TileBuilderArtifact(kind="switch_matrix_rtl", path=switch_matrix),
        TileBuilderArtifact(
            kind="switch_matrix_csv",
            path=tile_dir / f"{tile_name}_switch_matrix.csv",
        ),
        TileBuilderArtifact(kind="config_mem_csv", path=config_mem_csv),
        TileBuilderArtifact(kind="config_mem_rtl", path=config_mem),
        TileBuilderArtifact(kind="tile_rtl", path=tile_rtl),
    ]
    return [artifact for artifact in artifacts if artifact.path.exists()]


def _remove_legacy_matrix_artifacts(tile_dir: Path, tile_name: str) -> None:
    """Remove tile-builder matrix files from older variant naming.

    Parameters
    ----------
    tile_dir : Path
        Tile directory containing generated artifacts.
    tile_name : str
        Generated tile name.
    """
    for suffix in (".list", ".csv"):
        legacy_path = tile_dir / f"{tile_name}_baseline_switch_matrix{suffix}"
        if legacy_path.exists():
            legacy_path.unlink()


def _remove_stale_config_mem_csv(config_mem_csv: Path) -> None:
    """Remove a generated config-memory CSV before regenerating it.

    Parameters
    ----------
    config_mem_csv : Path
        Config-memory CSV path generated by FABulous.
    """
    if config_mem_csv.exists():
        config_mem_csv.unlink()


def _write_command_file(command_file: Path, tile_name: str, tile_dir: Path) -> None:
    """Write the FABulous commands represented by the builder run.

    Parameters
    ----------
    command_file : Path
        Command log path.
    tile_name : str
        Generated tile name.
    tile_dir : Path
        Generated tile directory.
    """
    _ = tile_dir
    command_file.write_text(
        "\n".join(
            [
                "load_fabric",
                f"gen_switch_matrix {tile_name}",
                f"gen_config_mem {tile_name}",
                f"gen_tile {tile_name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
