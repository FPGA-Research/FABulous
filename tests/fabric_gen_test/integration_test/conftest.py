"""Shared fixtures and cocotb-time helpers for FABulous integration tests."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import ciel.common
import cocotb
import pytest
from cocotb.handle import HierarchyObject, LogicObject
from cocotb.triggers import Timer
from cocotb.types import Logic, LogicArray
from dotenv import unset_key
from loguru import logger

import fabulous.fabric_files as _fab_template_pkg
import fabulous.fabulous_settings
from fabulous.fabric_definition.define import HDLType
from tests.conftest import make_default_project, run_cmd

if TYPE_CHECKING:
    from fabulous.fabulous_repl.fabulous_repl import FABulousREPL


@pytest.fixture(autouse=True)
def _disable_pdk_download(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Strip FAB_PDK / FAB_PDK_ROOT so RTL tests don't trigger PDK downloads.

    Gate-level (``@pytest.mark.gl``) tests are exempt — they consume an
    already-hardened project and explicitly need the PDK env vars to resolve
    standard-cell sim libraries.
    """
    if request.node.get_closest_marker("gl"):
        return

    monkeypatch.delenv("FAB_PDK", raising=False)
    monkeypatch.delenv("FAB_PDK_ROOT", raising=False)

    real_run = subprocess.run

    def scrubbing_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        result = real_run(*args, **kwargs)
        for env_file in tmp_path.rglob(".FABulous/.env"):
            unset_key(env_file, "FAB_PDK")
            unset_key(env_file, "FAB_PDK_ROOT")
        return result

    monkeypatch.setattr(subprocess, "run", scrubbing_run)


FRAME_BITS_PER_ROW: int = 32
MAX_FRAMES_PER_COL: int = 20
FRAME_SELECT_WIDTH: int = 5

BITSTREAM_START: int = 0xFAB0FAB1
DESYNC_FLAG: int = 20


class FabricConfigDUT(Protocol):
    """Structural protocol for a fabric DUT that exposes config-frame pins."""

    FrameData: LogicObject
    FrameStrobe: LogicObject


class FabricClockedDUT(FabricConfigDUT, Protocol):
    """Fabric DUT that also exposes the top-level ``UserCLK`` input."""

    UserCLK: LogicObject


# set_io <signal>[<index>] X<tile_x>Y<tile_y>/<bel>
_PCF_LINE_RE = re.compile(
    r"\s*set_io\s+(?P<signal>\w+)(\[(?P<index>\d+)?\])?\s+"
    r"X(?P<tilex>\d+)Y(?P<tiley>\d+)\/(?P<bel>\w+)"
)

# Tile_X<tile_x>Y<tile_y>_<bel>_<port>_top[<bit_index>]
_PORT_NAME_RE = re.compile(
    r"^Tile_X(?P<tilex>\d+)Y(?P<tiley>\d+)_(?P<bel>\w)_"
    r"(?P<port>I|O|T)_top(?P<bit>\d*)$",
    re.IGNORECASE,
)

# PCF semantic direction → FABulous bel top-port letter (I_top is fabric→pad,
# so reads from the fabric map to OUT; O_top is pad→fabric, so IN drives it).
_USE_TO_PORT: dict[str, str] = {"IN": "I", "OUT": "O", "EN": "T"}


class PCF:
    """Resolve user-design signals on a generated FABulous fabric DUT.

    A FABulous ``.pcf`` file maps a user-design signal name to a fabric
    location::

        set_io a[3]       X1Y2/A
        set_io clk        X3Y0/B

    `PCF` parses such a file, then walks the cocotb top-level handle
    to bind each ``<signal>[<index>]`` to the matching
    `Tile_X#Y#_<bel>_<use>_top` ports for `IN` (drive into fabric),
    `OUT`` (read from fabric) and ``EN`` (output-enable) directions. Tests
    can then drive or sample signals **by user name** instead of touching
    tile-relative ports, which keeps the test code portable across fabric
    layouts.

    Parameters
    ----------
    dut : HierarchyObject
        cocotb top-level handle for the fabric netlist (e.g. `eFPGA`).
    file : Path
        Path to a FABulous `.pcf` constraint file produced by the design
        flow (typically `<design>.pcf` or `.FABulous/template.pcf`).
    """

    def __init__(self, dut: HierarchyObject, file: Path) -> None:
        file = Path(file)
        self.top: str = dut._name  # noqa: SLF001
        self.signals: dict[str, dict[int, dict[str, LogicObject]]] = {}

        self._port_index: dict[tuple[str, str, str, str], LogicObject] = {}
        for element in dut:
            match = _PORT_NAME_RE.match(element._name)  # noqa: SLF001
            if match is None:
                continue
            key = (
                match.group("tilex"),
                match.group("tiley"),
                match.group("bel").lower(),
                match.group("port").lower(),
            )
            self._port_index[key] = element

        logger.info(f"Reading PCF file: {file}")
        with file.open("r") as pcf_file:
            for line in pcf_file:
                match = _PCF_LINE_RE.match(line)
                if match is None:
                    continue
                self._bind_line(match)

    def _bind_line(self, match: re.Match[str]) -> None:
        """Bind a single ``set_io`` line to the matching DUT ports."""
        signal = match.group("signal")
        index = int(match.group("index")) if match.group("index") is not None else 0
        tile_x = match.group("tilex")
        tile_y = match.group("tiley")
        bel = match.group("bel")

        dut_in = self._find_signal(tile_x, tile_y, bel, use="IN")
        dut_out = self._find_signal(tile_x, tile_y, bel, use="OUT")
        dut_en = self._find_signal(tile_x, tile_y, bel, use="EN")
        if dut_in is None or dut_out is None or dut_en is None:
            raise ValueError(
                f"PCF line maps {signal}[{index}] to X{tile_x}Y{tile_y}/{bel} "
                "but no matching IN/OUT/EN port was found on the DUT"
            )

        entry = {"IN": dut_in, "OUT": dut_out, "EN": dut_en}
        self.signals.setdefault(signal, {})[index] = entry
        self.signals[signal] = dict(sorted(self.signals[signal].items()))

    def _find_signal(
        self,
        tile_x: str,
        tile_y: str,
        bel: str,
        use: str,
    ) -> LogicObject | None:
        """Look up an indexed port by tile coordinates, bel letter and use."""
        key = (tile_x, tile_y, bel.lower(), _USE_TO_PORT[use].lower())
        return self._port_index.get(key)

    def get(self, signal: str, index: int | None = None) -> LogicArray | Logic:
        """Read the current ``IN`` value of ``signal``.

        Parameters
        ----------
        signal : str
            User-design signal name as it appears in the PCF.
        index : int | None, optional
            If ``None`` (default), the whole bus is returned as a
            :class:`LogicArray`. Otherwise a single bit as a :class:`Logic`.

        Returns
        -------
        LogicArray | Logic
            The signal value. If index is None, returns the whole bus as a
            :class:`LogicArray`. Otherwise a single :class:`Logic`.
        """
        if index is None:
            bits = "".join(
                str(bit["IN"].value) for bit in reversed(self.signals[signal].values())
            )
            return LogicArray(bits)
        return Logic(self.signals[signal][index]["IN"].value)

    def set(
        self,
        signal: str,
        value: LogicArray | Logic,
        index: int | None = None,
    ) -> None:
        """Drive ``value`` onto the ``OUT`` (fabric-input) pins of ``signal``.

        Parameters
        ----------
        signal : str
            User-design signal name as it appears in the PCF.
        value : LogicArray | Logic
            New value. Must be a :class:`LogicArray` of matching width when
            ``index`` is ``None``, otherwise a single :class:`Logic`.
        index : int | None, optional
            If given, only this bit is updated.
        """
        if index is None:
            for bit_index, bit in enumerate(reversed(value)):
                self.signals[signal][bit_index]["OUT"].value = bit
        else:
            self.signals[signal][index]["OUT"].value = value

    def get_raw(self, signal: str, use: str, index: int = 0) -> LogicObject:
        """Return the raw cocotb handle for a signal pin.

        Use this when you need a handle for triggers (e.g. ``RisingEdge``) or
        for clocking a generated clock onto a routed input.

        Parameters
        ----------
        signal : str
            User-design signal name.
        use : str
            ``"IN"``, ``"OUT"`` or ``"EN"``.
        index : int, optional
            Bit index. Default ``0``.

        Returns
        -------
        LogicObject
            The raw cocotb handle.
        """
        return self.signals[signal][index][use]


async def zero_bitstream(dut: FabricConfigDUT, delay_ns: int = 10) -> None:
    """Drive an all-zeros frame across every column to clear configuration.

    Useful before loading a new user design to scrub any latched config bits
    from a previous test, which can otherwise leave combinational loops in
    the routing fabric.

    Parameters
    ----------
    dut : FabricConfigDUT
        cocotb top-level handle exposing ``FrameData`` and ``FrameStrobe``.
    delay_ns : int, optional
        Duration each phase is held, in nanoseconds. Default ``10``.
    """
    dut.FrameData.value = 0
    dut.FrameStrobe.value = (1 << len(dut.FrameStrobe)) - 1
    await Timer(delay_ns, unit="ns")

    dut.FrameStrobe.value = 0
    await Timer(delay_ns, unit="ns")


async def upload_bitstream(
    dut: FabricConfigDUT,
    bitstream_path: Path,
    delay_ns: int = 10,
    num_data_rows: int | None = None,
) -> None:
    """Stream a `.bin` bitstream file into the fabric configuration ports.

    Parameters
    ----------
    dut : FabricConfigDUT
        cocotb top-level handle exposing `FrameData` and `FrameStrobe`.
    bitstream_path : Path
        Path to a FABulous `.bin` bitstream.
    delay_ns : int, optional
        Duration each strobe is held high (and then low) per row, in
        nanoseconds. Default `10`.
    num_data_rows : int | None, optional
        Number of 32-bit row words per frame in the bitstream payload.

    Raises
    ------
    ValueError
        If the file ends before the sync word is found.
    """
    bitstream_path = Path(bitstream_path)
    logger.info(f"Uploading bitstream: {bitstream_path}")

    framedata_bits = len(dut.FrameData)
    framestrobe_bits = len(dut.FrameStrobe)
    rows_per_frame = (
        num_data_rows
        if num_data_rows is not None
        else framedata_bits // FRAME_BITS_PER_ROW
    )

    with bitstream_path.open("rb") as f:
        synced = False
        while data := f.read(4):
            if int.from_bytes(data, "big") == BITSTREAM_START:
                logger.debug("Detected bitstream start marker")
                synced = True
                break
        if not synced:
            raise ValueError(
                f"Sync word 0x{BITSTREAM_START:08X} not found in {bitstream_path}"
            )

        while True:
            data = f.read(4)
            if not data:
                logger.warning(
                    f"Bitstream {bitstream_path} ended without a DESYNC header"
                )
                break

            header = int.from_bytes(data, "big")
            column_select = (header >> 27) & 0x1F
            sync_bit = (header >> DESYNC_FLAG) & 0x1
            frame_strobe = header & 0xFFFFF

            if sync_bit:
                logger.debug("Detected DESYNC flag, ending upload")
                break

            all_row_data = 0
            for _ in range(rows_per_frame):
                row_word = int.from_bytes(f.read(4), "big")
                all_row_data = (all_row_data << FRAME_BITS_PER_ROW) | row_word

            dut.FrameData.value = all_row_data << FRAME_BITS_PER_ROW
            dut.FrameStrobe.value = frame_strobe << (MAX_FRAMES_PER_COL * column_select)
            await Timer(delay_ns, unit="ns")

            dut.FrameStrobe.value = 0
            await Timer(delay_ns, unit="ns")

        logger.info(f"Bitstream upload completed ({framestrobe_bits} strobe bits)")

        dut.FrameData.value = 0
        dut.FrameStrobe.value = 0
        await Timer(delay_ns, unit="ns")


async def setup_fabric(dut: FabricConfigDUT, settle_ns: int = 10) -> PCF:
    """Bring up the fabric DUT and return a parsed PCF.

    Reads the PCF / bitstream / row-count paths the pytest fixture handed
    over via `cocotb.plusargs` (`FAB_PCF`, `FAB_BIT`,
    `FAB_NUM_DATA_ROWS`), zeros the configuration, streams the bitstream
    in, and waits `settle_ns` between each phase so combinational paths
    propagate.

    Returns the :class:`PCF` so tests can drive/sample by user-design
    signal name without repeating the boilerplate.

    Parameters
    ----------
    dut : FabricConfigDUT
        cocotb top-level handle.
    settle_ns : int, optional
        Per-phase settling delay in ns. Default ``10``.

    Returns
    -------
    PCF
        A parsed PCF object for driving/sampling signals by user-design
        signal name.
    """
    pcf = PCF(dut, Path(cocotb.plusargs["FAB_PCF"]))
    await zero_bitstream(dut)
    await Timer(settle_ns, unit="ns")
    await upload_bitstream(
        dut,
        Path(cocotb.plusargs["FAB_BIT"]),
        num_data_rows=int(cocotb.plusargs["FAB_NUM_DATA_ROWS"]),
    )
    await Timer(settle_ns, unit="ns")
    return pcf


def _collect_fabric_sources(project_dir: Path, suffix: str) -> list[Path]:
    """Return every HDL source emitted under ``Fabric/`` and ``Tile/``.

    FABulous emits the same module (e.g. ``Config_access.v``) under multiple
    tile directories with identical content; deduplicate by basename so the
    simulator sees one definition per module name.
    """
    # NVC rejects forward references, so the models_pack package must come first.
    fabric_paths = sorted((project_dir / "Fabric").glob(f"*{suffix}"))
    package_paths = [p for p in fabric_paths if p.stem == "models_pack"]
    other_fabric_paths = [p for p in fabric_paths if p.stem != "models_pack"]

    sources: list[Path] = []
    seen_names: set[str] = set()
    for path in (
        *package_paths,
        *sorted((project_dir / "Tile").rglob(f"*{suffix}")),
        *other_fabric_paths,
    ):
        if path.name in seen_names:
            logger.debug(f"Skipping duplicate-named fabric source: {path}")
            continue
        seen_names.add(path.name)
        sources.append(path)
    return sources


def set_multiplexer_style(project_dir: Path, style: str) -> None:
    """Rewrite the ``MultiplexerStyle`` value in a project's ``fabric.csv``.

    Flips the switch-matrix mux style the generated fabric will use (``custom``
    or ``generic``) by editing only the value column of the
    ``MultiplexerStyle`` row, leaving the trailing comment columns intact. The
    edit happens before ``load_fabric`` so the real ``parse_csv`` path consumes
    it rather than the in-memory model being mutated.

    Parameters
    ----------
    project_dir : Path
        FABulous project directory containing ``fabric.csv``.
    style : str
        New multiplexer style, e.g. ``"custom"`` or ``"generic"``.

    Raises
    ------
    ValueError
        If ``fabric.csv`` has no ``MultiplexerStyle`` row.
    """
    fabric_csv = project_dir / "fabric.csv"
    lines = fabric_csv.read_text().splitlines()
    for i, line in enumerate(lines):
        fields = line.split(",")
        if fields[0].strip() == "MultiplexerStyle":
            fields[1] = style
            lines[i] = ",".join(fields)
            fabric_csv.write_text("\n".join(lines) + "\n")
            return
    raise ValueError(f"No MultiplexerStyle row found in {fabric_csv}")


_USER_DESIGNS_DIR = Path(__file__).resolve().parent / "user_designs"
_USER_DESIGNS_PCF = _USER_DESIGNS_DIR / "constraints.pcf"

_USER_DESIGN_SUFFIXES: dict[HDLType, tuple[str, ...]] = {
    HDLType.VERILOG: (".v", ".sv"),
    HDLType.VHDL: (".vhdl", ".vhd"),
}


def stage_user_design(
    project_dir: Path,
    design_name: str,
    lang: HDLType = HDLType.VERILOG,
) -> tuple[Path, Path]:
    """Copy a packaged user design + PCF into ``project_dir/user_design/``.

    Looks for ``user_designs/<design_name>.<ext>`` (extension chosen from
    ``lang``), copies it next to a fresh empty ``top_wrapper.v`` and a copy
    of the shared ``constraints.pcf`` renamed to ``<design_name>.pcf``.

    Parameters
    ----------
    project_dir : Path
        The project directory to stage the user design into.
    design_name : str
        Basename of the packaged design under ``user_designs/``.
    lang : HDLType, optional
        Source language to select the file extension. Default
        ``HDLType.VERILOG``.

    Returns
    -------
    tuple[Path, Path]
        ``(user_design_path, pcf_path)`` inside the project — both ready to
        be passed to :func:`compile_user_design`.

    Raises
    ------
    FileNotFoundError
        If no source file matching ``design_name`` and ``lang`` exists.
    """
    suffixes = _USER_DESIGN_SUFFIXES[lang]
    candidates = [_USER_DESIGNS_DIR / f"{design_name}{ext}" for ext in suffixes]
    source_file = next((p for p in candidates if p.exists()), None)
    if source_file is None:
        tried = ", ".join(c.name for c in candidates)
        raise FileNotFoundError(
            f"No {lang.value} source for design '{design_name}' (tried: {tried})"
        )

    user_design_dir = project_dir / "user_design"
    user_design_dir.mkdir(exist_ok=True)
    user_design = user_design_dir / source_file.name
    pcf = user_design_dir / f"{design_name}.pcf"

    shutil.copy(source_file, user_design)
    shutil.copy(_USER_DESIGNS_PCF, pcf)
    (user_design_dir / "top_wrapper.v").write_text("")
    return user_design, pcf


def compile_user_design(
    cli: "FABulousREPL",
    user_design: Path,
    design_name: str,
    pcf: Path,
) -> Path:
    """Drive ``compile_design`` through Yosys + nextpnr + bitgen.

    Mirrors what ``test_design_pattern`` (RTL) and ``test_design_pattern_gl``
    (GL) both need: synthesise the user design against the loaded fabric,
    place-and-route under the supplied PCF, generate the bitstream binary,
    and surface a clear failure if the binary is missing.

    Parameters
    ----------
    cli : FABulousREPL
        The CLI instance with the target fabric already loaded.
    user_design : Path
        Path to the staged user design source to compile.
    design_name : str
        Top-level module name passed to ``compile_design``.
    pcf : Path
        Pin constraints file forwarded to nextpnr.

    Returns
    -------
    Path
        The ``.bin`` bitstream produced next to ``user_design``.

    Raises
    ------
    FileNotFoundError
        If ``compile_design`` does not produce the expected bitstream.
    """
    run_cmd(
        cli,
        f"compile_design {user_design} -top {design_name} "
        f'--synth-extra-args=-iopad --nextpnr-extra-args "-o pcf={pcf}"',
    )
    bitstream = user_design.with_suffix(".bin")
    if not bitstream.exists():
        raise FileNotFoundError(f"compile_design did not produce {bitstream}")
    return bitstream


# ---------------------------------------------------------------------------
# Gate-level (GL) simulation fixtures
# ---------------------------------------------------------------------------
# GL tests consume a fabric that has already been hardened by the FABulous
# LibreLane flow (the same flow that gds-flow-ci.yml publishes as
# fabric-output-<pdk>.tar.zst). Provide the hardened project either as a CLI
# option or as an env var:
#
#     pytest --gl --gl-fabric-project=/path/to/test_project
#     FAB_GL_FABRIC_PROJECT=/path/to/test_project pytest --gl
#
# PDK sim-cell libs are resolved from FAB_PDK + (FAB_PDK_ROOT or ciel default).
# Override with `--gl-sim-libs=<glob>` (repeatable).

_VERILOG_TEMPLATE_TEST_DIR = (
    Path(_fab_template_pkg.__file__).resolve().parent
    / "FABulous_project_template_verilog"
    / "Test"
)
_COMMON_TEMPLATE_TEST_DIR = (
    Path(_fab_template_pkg.__file__).resolve().parent
    / "FABulous_project_template_common"
    / "Test"
)


def pytest_addoption(parser: pytest.Parser) -> None:  # type: ignore[name-defined]
    """Register GL-only knobs.

    ``--gl`` and ``--gl-fabric-project`` are registered in the repo-level
    ``tests/conftest.py``; ``--gl-sim-libs`` is GL-specific and lives here.
    """
    group = parser.getgroup("FABulous GL simulation")
    group.addoption(
        "--gl-sim-libs",
        action="append",
        default=[],
        help="Verilog sim-cell library file or glob (repeatable). When unset "
        "the test resolves the PDK std-cell models from FAB_PDK / FAB_PDK_ROOT "
        "in the project .env.",
    )


@pytest.fixture
def gl_fabric_project(pytestconfig: pytest.Config) -> Path:
    """Resolve the hardened FABulous project supplied via CLI or env var.

    Skips the test (rather than failing) when neither is set, so the suite is
    safe to schedule unconditionally.
    """
    raw: str | None = pytestconfig.getoption("gl_fabric_project") or os.environ.get(
        "FAB_GL_FABRIC_PROJECT"
    )
    if not raw:
        pytest.skip(
            "GL simulation needs a hardened fabric project: pass "
            "--gl-fabric-project=<path> or set FAB_GL_FABRIC_PROJECT. The "
            "fabric-output-<pdk> artifact published by gds-flow-ci.yml unpacks "
            "into the expected layout."
        )
    project = Path(raw).expanduser().resolve()
    if not project.is_dir():
        pytest.fail(f"--gl-fabric-project={project} is not a directory")
    if not (project / ".FABulous").is_dir():
        pytest.fail(
            f"{project} is not a FABulous project (missing .FABulous/). Did "
            "you point at the right unpacked artifact?"
        )
    return project


def _ignore_heavy_artifacts(src_dir: str, names: list[str]) -> set[str]:
    """``shutil.copytree`` filter that skips LibreLane run output.

    Hardened projects can be tens of GB because every Tile/ holds the full
    librelane ``runs/`` tree plus per-macro snapshots. ``run_simulation --gl``
    only reads the netlists under each ``macro/final_views/`` (see
    ``collect_gl_sources``), so keep that subtree and drop the rest of
    ``macro/`` along with ``runs/`` and ``gds/`` to keep the per-test copy
    cheap.
    """
    skip = {"runs", "gds", ".git", "__pycache__"}
    ignored = {n for n in names if n in skip}
    # macro/ holds the final_views netlists the GL flow resolves alongside
    # heavy intermediate snapshots; keep only final_views.
    if Path(src_dir).name == "macro":
        ignored |= {n for n in names if n != "final_views"}
    return ignored


@pytest.fixture
def hardened_project_copy(
    gl_fabric_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Per-test copy of the hardened project, with Test/ refreshed.

    ``compile_design`` mutates ``user_design/`` and writes intermediate files
    into ``.FABulous/``, so the supplied artifact is copied into a fresh tmp
    dir first to keep it untouched and to allow parallel runs. The copy
    drops the heavy librelane artifacts (``runs/``, ``gds/`` and the
    non-``final_views`` parts of each ``macro/``) but keeps the
    ``macro/final_views`` netlists, since ``run_simulation --gl`` resolves
    the gate-level sources from the copy (see ``collect_gl_sources``).

    The Test/ Taskfile is taken from the **current** FABulous template rather
    than what shipped with the artifact, because the compile_design contract
    evolves with the Python code.
    """
    dest = tmp_path / "fabric_project"
    shutil.copytree(
        gl_fabric_project,
        dest,
        symlinks=False,
        ignore=_ignore_heavy_artifacts,
    )

    test_dir = dest / "Test"
    test_dir.mkdir(exist_ok=True)
    for src in _VERILOG_TEMPLATE_TEST_DIR.iterdir():
        if src.is_file():
            shutil.copy2(src, test_dir / src.name)
    for src in _COMMON_TEMPLATE_TEST_DIR.iterdir():
        if src.is_file():
            shutil.copy2(src, test_dir / src.name)

    # The repo-level autouse fixture stubs ``get_ciel_home`` to a hermetic tmp
    # dir (with only an ihp placeholder) so unit tests never touch the real PDK
    # store. GL simulation needs the real standard-cell models, so restore the
    # genuine ciel resolver, which froze the real ciel home at import time.
    monkeypatch.setattr(
        fabulous.fabulous_settings, "get_ciel_home", ciel.common.get_ciel_home
    )

    monkeypatch.setenv("FAB_PROJ_DIR", str(dest))
    return dest


@pytest.fixture
def fabulous_project(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Marker-aware override of the global ``fabulous_project`` fixture.

    ``@pytest.mark.gl`` tests get the per-test copy of the user's hardened
    LibreLane project (so the ``cli`` fixture binds to it transparently);
    every other test in this directory falls back to a fresh empty project,
    matching the global behaviour from ``tests/conftest.py``.

    The override has to live here (rather than as a ``cli`` override) because
    the ``cli`` fixture is verilog-only and the lookup happens via
    ``fabulous_project``; intercepting at that hop lets GL tests reuse ``cli``
    without further wiring.
    """
    if request.node.get_closest_marker("gl"):
        return request.getfixturevalue("hardened_project_copy")

    return make_default_project(tmp_path, monkeypatch)
