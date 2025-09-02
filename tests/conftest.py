"""Global pytest configuration and fixtures for all FABulous tests."""

import os
import shutil
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Protocol

import pytest
from _pytest.logging import LogCaptureFixture
from cocotb_tools.runner import get_runner
from loguru import logger

import fabulous.fabulous
import fabulous.fabulous_settings
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction, HDLType, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import Port
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_repl.helper import create_project, setup_logger
from fabulous.fabulous_settings import init_context, reset_context

VERILOG_SOURCE_PATH = (
    Path(__file__).parent.parent
    / "fabulous"
    / "fabric_files"
    / "FABulous_project_template_verilog"
)

VHDL_SOURCE_PATH = (
    Path(__file__).parent.parent
    / "fabulous"
    / "fabric_files"
    / "FABulous_project_template_vhdl"
)


class CocotbRunner(Protocol):
    """Callable Protocol for our cocotb runner fixture.

    The runner is called with keyword-only arguments. Protocol structural typing
    allows any compatible callable to satisfy this contract.
    """

    def __call__(
        self,
        *,
        sources: list[Path],
        hdl_top_level: str,
        test_module_path: Path,
    ) -> None:  # pragma: no cover - typing only
        ...


@pytest.fixture
def cocotb_runner(tmp_path: Path) -> CocotbRunner:
    """Factory fixture to create cocotb runners for RTL simulation."""

    def _create_runner(
        sources: list[Path], hdl_top_level: str, test_module_path: Path
    ) -> None:
        """Build and run a cocotb simulation.

        Inject correct model pack file for each language (verilog: models_pack.v,
        vhdl: models_pack.vhdl) if not already supplied, replacing the previous
        reference to a non-existent tests/testdata directory.
        """
        if not sources:
            raise ValueError("No HDL sources provided")

        lang = {p.suffix for p in sources}
        if len(lang) > 1:
            raise ValueError("All source files must have the same HDL language suffix")
        hdl_toplevel_lang = lang.pop()
        if hdl_toplevel_lang not in {".v", ".sv", ".vhdl", ".vhd"}:
            raise ValueError(f"Unsupported HDL language: {hdl_toplevel_lang}")

        sim = {".v": "icarus", ".sv": "icarus", ".vhdl": "ghdl", ".vhd": "ghdl"}[
            hdl_toplevel_lang
        ]

        # No graceful skip: allow missing simulator to raise error for visibility

        # Ensure model pack file is present for primitives if not explicitly provided
        if hdl_toplevel_lang == ".v":
            model_pack_path = VERILOG_SOURCE_PATH / "Fabric" / "models_pack.v"
        else:  # .vhdl or .vhd
            model_pack_path = VHDL_SOURCE_PATH / "Fabric" / "models_pack.vhdl"

        # Only add if not already one of the provided sources (compare resolved paths)
        resolved_sources = {p.resolve() for p in sources}
        if (
            model_pack_path.exists()
            and model_pack_path.resolve() not in resolved_sources
        ):
            # Prepend so dependencies are available early
            sources.insert(0, model_pack_path)

        # Avoid errors when reading 'X'/'Z' by telling cocotb how to resolve them
        # Options: ZEROS, ONES, RANDOM, VALUE_ERROR. Pick ZEROS for deterministic tests.
        os.environ.setdefault("COCOTB_RESOLVE_X", "ZEROS")

        runner = get_runner(sim)

        # Copy test module to temp directory for cocotb
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)

        # Copy this test file to the test directory so cocotb can find it
        shutil.copy(test_module_path, test_dir / test_module_path.name)

        # Build directory
        build_dir = tmp_path / "cocotb_build"

        # Configure sources based on HDL language
        # GHDL flags for VHDL-2008 and IEEE extensions
        ghdl_flags: list[str] = []

        if hdl_toplevel_lang == ".v":
            runner.build(
                sources=sources,
                hdl_toplevel=hdl_top_level,
                always=True,
                build_dir=build_dir,
                defines={"NOTIMESCALE": 1},
                timescale=("1ns", "1ps"),  # Set simulation time unit/precision
            )
        else:  # .vhdl or .vhd
            # GHDL converts identifiers to lowercase for elaboration and execution
            hdl_top_level = hdl_top_level.lower()
            ghdl_flags = ["--std=08", "--ieee=synopsys"]
            runner.build(
                sources=sources,
                hdl_toplevel=hdl_top_level,
                always=True,
                build_dir=build_dir,
                defines={"NOTIMESCALE": 1},
                build_args=ghdl_flags,  # VHDL-2008 & IEEE extensions
                timescale=("1ns", "1ps"),
            )

            # GHDL mcode backend requires running from the build directory.
            # Copy the test module to build_dir and run tests from there.
            shutil.copy(test_module_path, build_dir / test_module_path.name)
            test_dir = build_dir

        # GHDL mcode backend requires --std and --ieee flags during run as well,
        # otherwise it cannot find entities compiled with those options.
        test_args = ghdl_flags if sim == "ghdl" else []

        runner.test(
            hdl_toplevel=hdl_top_level,
            test_module=test_module_path.stem,
            build_dir=build_dir,
            test_dir=test_dir,
            test_args=test_args,
        )

    return _create_runner


def sjump_port(
    name: str,
    inOut: IO,
    wireCount: int = 2,
    xOffset: int = 0,
    yOffset: int = 0,
) -> Port:
    """Build an SJUMP port.

    OUTPUT ports drive `sourceName`; INPUT ports terminate at
    `destinationName`. SJUMP ports carry zero offsets, which is exactly the
    case the width fix in `expandPortInfo*` has to handle.
    """
    return Port(
        wireDirection=Direction.SJUMP,
        sourceName=name if inOut == IO.OUTPUT else "NULL",
        xOffset=xOffset,
        yOffset=yOffset,
        destinationName=name if inOut == IO.INPUT else "NULL",
        wireCount=wireCount,
        name=name,
        inOut=inOut,
        sideOfTile=Side.ANY,
    )


def make_empty_tile(
    name: str,
    ports: list[Port] | None = None,
    *,
    tileDir: Path = Path(),
    matrixDir: Path = Path(),
    pinOrderConfig: dict | None = None,
    config_bits: int = 0,
) -> Tile:
    """Build a minimal Tile usable inside a SuperTile.tileMap.

    Passing `pinOrderConfig={}` skips the GDS pin-order import; the `None`
    default preserves the original behaviour for callers that don't care.
    `config_bits` sets the switch matrix's declared config-bit count so the
    tile reports it via `globalConfigBits`.
    """
    return Tile(
        name=name,
        ports=ports or [],
        bels=[],
        tileDir=tileDir,
        switch_matrix=SwitchMatrix(
            matrix_file=matrixDir, connections={}, hdl_config_bits=config_bits or None
        ),
        gen_ios=[],
        userCLK=False,
        pinOrderConfig=pinOrderConfig,
    )


def make_muladd_bel(internal: list[tuple[str, IO]], *, prefix: str = "SUPER_") -> Bel:
    """Build a MULADD-style supertile BEL with only its internal pins populated."""
    return Bel(
        src=Path("MULADD.v"),
        prefix=prefix,
        module_name="MULADD",
        internal=internal,
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )


def pytest_addoption(parser: pytest.Parser) -> None:  # type: ignore[name-defined]
    """Register opt-in flags for the marker-gated test buckets.

    Usage:
        pytest --runslow
        pytest --gl --gl-fabric-project=<path>

    Without these flags, tests marked ``@pytest.mark.slow`` /
    ``@pytest.mark.gl`` are excluded via the default ``addopts`` filter in
    ``pyproject.toml``.
    """
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run tests marked as slow (overrides default '-m not slow')",
    )
    parser.addoption(
        "--gl",
        action="store_true",
        default=False,
        help="run gate-level (GL) simulation tests; requires a fabric project "
        "hardened by the GDS flow (see --gl-fabric-project)",
    )
    parser.addoption(
        "--gl-fabric-project",
        action="store",
        default=None,
        help="path to a FABulous project that has been run through "
        "`gen_fabric_macro` (must contain Fabric/macro/final_views/). "
        "May also be supplied via the FAB_GL_FABRIC_PROJECT env var. "
        "Typically the unpacked `fabric-output-<pdk>` artifact from "
        "gds-flow-ci.yml.",
    )


def pytest_configure(config: pytest.Config) -> None:  # type: ignore[name-defined]
    user_args = config.invocation_params.args
    if any(a.startswith(("-m", "--markexpr")) for a in user_args):
        return
    exclude = []
    if not config.getoption("runslow"):
        exclude.append("not slow")
    if not config.getoption("gl"):
        exclude.append("not gl")
    config.option.markexpr = " and ".join(exclude)


def normalize(block: str) -> list[str]:
    """Normalize a block of text to perform comparison.

    Strip newlines from the very beginning and very end, then split into separate lines
    and strip trailing whitespace from each line.
    """
    assert isinstance(block, str)
    block = block.strip("\n")
    return [line.rstrip() for line in block.splitlines()]


def run_cmd(app: FABulousREPL, cmd: str) -> None:
    """Run a command in the given FABulousREPL instance."""
    app.onecmd_plus_hooks(cmd)


def normalize_and_check_for_errors(caplog_text: str) -> list[str]:
    """Normalize a block of text and check for errors."""
    log = normalize(caplog_text)
    assert not any("ERROR" in line for line in log), "Error found in log messages"
    return log


def make_fabric_from_grid(grid: list[list[Tile | None]]) -> Fabric:
    """Build a real Fabric from a row-major grid of Tile/None positions.

    `numberOfRows`/`numberOfColumns` are derived from the grid shape and
    `tileDic`` gets one entry per distinct tile name, so the fabric behaves
    like a CSV-parsed one without going through the parser.

    Parameters
    ----------
    grid : list[list[Tile | None]]
        Row-major tile placement; `None` marks an empty (NULL) cell.

    Returns
    -------
    Fabric
        A real Fabric populated from the grid.
    """
    tile_dic: dict[str, Tile] = {}
    for row in grid:
        for tile in row:
            if tile is not None:
                tile_dic.setdefault(tile.name, tile)
    return Fabric(
        fabric_dir=Path("/tmp"),
        tile=grid,
        numberOfRows=len(grid),
        numberOfColumns=len(grid[0]) if grid else 0,
        tileDic=tile_dic,
    )


@pytest.fixture(autouse=True)
def fabulous_test_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[None]:
    """Set up global test environment for FABulous tests."""
    fabulous_root = str(Path(__file__).resolve().parent.parent / "FABulous")

    # FAB_GL_FABRIC_PROJECT selects the hardened project for the GL suite; it
    # is test-control input, not project state, so it must survive the scrub.
    for key in list(os.environ.keys()):
        if key.startswith("FAB_") and key != "FAB_GL_FABRIC_PROJECT":
            monkeypatch.delenv(key, raising=False)

    fake_user_config_dir = tmp_path / ".fabulous"

    monkeypatch.setenv("FAB_ROOT", fabulous_root)
    monkeypatch.setenv("FABULOUS_TESTING", "TRUE")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda _: tmp_path)
    monkeypatch.setattr(
        fabulous.fabulous_settings, "FAB_USER_CONFIG_DIR", fake_user_config_dir
    )
    monkeypatch.setattr(fabulous.fabulous, "FAB_USER_CONFIG_DIR", fake_user_config_dir)
    monkeypatch.setattr(
        fabulous.fabulous_settings.ciel.manage,
        "enable",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        fabulous.fabulous_settings,
        "get_ciel_home",
        lambda: str(tmp_path / ".ciel"),
    )
    (tmp_path / ".ciel" / "ihp-sg13g2").mkdir(parents=True, exist_ok=True)
    setup_logger(0, False)

    yield

    reset_context()


def make_default_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fresh empty Verilog project and point ``FAB_PROJ_DIR`` at it.

    Shared by the base ``fabulous_project`` fixture and any nested-conftest
    override that needs to reproduce the default (non-overridden) behaviour
    without re-entering the fixture by name.
    """
    project_dir = tmp_path / "test_project"
    monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
    create_project(project_dir)
    return project_dir


@pytest.fixture
def fabulous_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A FABulous project the ``cli`` fixture should bind to.

    Default behaviour creates a fresh empty Verilog project under
    ``tmp_path``. Override this fixture in a nested conftest to point ``cli``
    at a different project — e.g. the GL suite overrides it to return the
    per-test copy of a hardened LibreLane project. The override is what lets
    GL tests reuse the global ``cli`` fixture without any further plumbing.
    """
    return make_default_project(tmp_path, monkeypatch)


@pytest.fixture
def cli(fabulous_project: Path) -> FABulousREPL:
    """Create a FABulous CLI instance bound to ``fabulous_project``."""
    init_context(fabulous_project)
    cli = FABulousREPL(
        "verilog",
        force=False,
        interactive=False,
        verbose=False,
        debug=True,
    )
    cli.debug = True
    run_cmd(cli, "load_fabric")
    return cli


@pytest.fixture(autouse=True)
def cleanup_logger() -> Generator[None]:
    """Ensure logger is properly cleaned up.

    Run after each test to prevent 'logging to closed file' errors when tests exit
    quickly.
    """
    yield
    logger.remove()


@pytest.fixture
def caplog(caplog: LogCaptureFixture) -> LogCaptureFixture:
    """Caplog fixture that integrates with loguru."""
    logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,  # Set to 'True' if your test is spawning child processes.
    )
    return caplog


@pytest.fixture
def project_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Path]:
    """Return a callable that creates a FABulous project in a temp directory.

    The returned callable accepts `lang` to choose Verilog vs VHDL and an
    optional `name` for the directory (default `test_project`). It also
    chdirs into the temp directory and sets `FAB_PROJ_DIR` via monkeypatch
    so context lookups resolve to the newly created project.
    """

    def _create(lang: HDLType = HDLType.VERILOG, name: str = "test_project") -> Path:
        project_dir = tmp_path / name
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
        create_project(project_dir, lang=lang)
        return project_dir

    return _create


@pytest.fixture
def project(project_factory: Callable[..., Path]) -> Path:
    """Verilog FABulous project in a temp directory."""
    return project_factory()


@pytest.fixture
def project_vhdl(project_factory: Callable[..., Path]) -> Path:
    """VHDL FABulous project in a temp directory."""
    return project_factory(lang=HDLType.VHDL)
