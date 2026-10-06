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
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_repl.helper import create_project, setup_logger
from fabulous.fabulous_settings import init_context, reset_context


class CocotbRunner(Protocol):
    """Signature of the `cocotb_runner` fixture's callable."""

    def __call__(
        self,
        *,
        sources: list[Path],
        hdl_top_level: str,
        test_module_path: Path,
        plusargs: list[str] | None = None,
        testcase: str | None = None,
    ) -> None:  # pragma: no cover - typing only
        ...


@pytest.fixture
def cocotb_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CocotbRunner:
    """Create cocotb runners for RTL simulation."""

    def _create_runner(
        *,
        sources: list[Path],
        hdl_top_level: str,
        test_module_path: Path,
        plusargs: list[str] | None = None,
        testcase: str | None = None,
    ) -> None:
        lang = set([i.suffix for i in sources])

        if len(lang) > 1:
            raise ValueError("All source files must have the same HDL language suffix")

        hdl_toplevel_lang = lang.pop()
        if hdl_toplevel_lang == ".v":
            sim, test_lang = "icarus", "verilog"
        elif hdl_toplevel_lang in {".vhd", ".vhdl"}:
            test_lang = "vhdl"
            if shutil.which("nvc") is not None:
                sim = "nvc"
            elif shutil.which("ghdl") is not None:
                sim = "ghdl"
                hdl_top_level = hdl_top_level.lower()
            else:
                raise RuntimeError("No VHDL simulator available: install nvc or ghdl.")
        else:
            raise ValueError(f"Unsupported HDL language: {hdl_toplevel_lang}")
        runner = get_runner(sim)

        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)

        shutil.copy(test_module_path, test_dir / test_module_path.name)

        # cocotb_tools.runner exports the parent's sys.path to the simulator
        # subprocess as PYTHONPATH; prepend test_dir so the copied test module
        # imports as a top-level module by its stem.
        monkeypatch.syspath_prepend(str(test_dir))

        build_dir = tmp_path / "cocotb_build"
        build_kwargs: dict = {
            "sources": sources,
            "hdl_toplevel": hdl_top_level,
            "always": True,
            "build_dir": build_dir,
        }
        if test_lang == "verilog":
            build_kwargs["timescale"] = ("1ps", "1ps")
        elif sim == "nvc":
            build_kwargs["build_args"] = [
                "--std=2008",
                "-H",
                "2g",
                "-M",
                "1g",
                "--ieee-warnings=off",
            ]
        runner.build(**build_kwargs)

        if sim == "ghdl":
            for file in build_dir.iterdir():
                if file.is_file():
                    shutil.copy(file, test_dir / file.name)

        runner.test(
            hdl_toplevel=hdl_top_level,
            hdl_toplevel_lang=test_lang,
            test_module=test_module_path.stem,
            plusargs=plusargs or [],
            testcase=testcase,
        )

    return _create_runner


def sjump_port(
    name: str,
    in_out: IO,
    wire_count: int = 2,
    x_offset: int = 0,
    y_offset: int = 0,
) -> TilePort:
    """Build an SJUMP port.

    OUTPUT ports drive `source_name`; INPUT ports terminate at
    `destination_name`. SJUMP ports carry zero offsets, which is exactly the
    case the width fix in `expand_port_info*` has to handle.
    """
    return TilePort(
        name=name,
        io_direction=in_out,
        width=wire_count,
        side_of_tile=Side.ANY,
        wire_direction=Direction.SJUMP,
        source_name=name if in_out == IO.OUTPUT else "NULL",
        x_offset=x_offset,
        y_offset=y_offset,
        destination_name=name if in_out == IO.INPUT else "NULL",
        wire_count=wire_count,
    )


def make_empty_tile(
    name: str,
    ports: list[TilePort] | None = None,
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
        "`gen_macro stitch` (must contain Fabric/macro/final_views/). "
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
    (tmp_path / ".ciel" / "ihp-sg13").mkdir(parents=True, exist_ok=True)
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
