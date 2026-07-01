"""Pytest configuration for CLI tests."""

import hashlib
import re
import subprocess
from pathlib import Path

import pytest
from dotenv import set_key
from pytest_mock import MockerFixture

from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from tests.conftest import run_cmd

TILE = "LUT4AB"

MOCK_COMPLETED_PROCESS = subprocess.CompletedProcess(args=[], returncode=0)

# The end-to-end CLI tests (fabric/tile generation, compile, simulation) each
# load the same demo fabric, which synthesises every BEL HDL file with Yosys,
# one subprocess per file. Every test runs against a fresh copy of the demo, so
# the identical BEL sources would otherwise be re-synthesised dozens of times
# across the suite. These regexes pull the source and JSON output paths out of
# the Yosys command FABulous builds in
# ``fabulous.fabric_definition.yosys_obj.YosysJson``.
_YOSYS_SRC_RE = re.compile(r"read_verilog\s+-sv\s+([^;\s]+)")
_YOSYS_OUT_RE = re.compile(r"write_json\s+-compat-int\s+([^;\s]+)")


@pytest.fixture(scope="session")
def _yosys_json_cache() -> dict[str, bytes]:
    """Session cache mapping BEL source content hashes to Yosys JSON output."""
    return {}


@pytest.fixture(autouse=True)
def cache_yosys_synthesis(
    _yosys_json_cache: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Memoise Yosys BEL synthesis by source content for the test session.

    Each unique BEL source is synthesised by the real Yosys once; identical
    sources copied into later test projects reuse the cached JSON instead of
    spawning Yosys again. The produced JSON is byte-identical to a real Yosys
    run, and every ``YosysJson`` still builds its own objects from it, so no
    parsed state is shared between tests. The fabric still loads and generates
    for real, so the end-to-end smoke tests keep their meaning.
    """
    real_run = subprocess.run

    def cached_run(
        cmd: list[str] | str, *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess:
        # Only the Yosys BEL-synthesis call is cached. Every other subprocess
        # (ghdl, iverilog/nvc, `task`, install, ...) must run untouched, so
        # require the executable to be Yosys before inspecting the arguments.
        if not isinstance(cmd, (list, tuple)) or not cmd:
            return real_run(cmd, *args, **kwargs)
        if "yosys" not in Path(str(cmd[0])).name.lower():
            return real_run(cmd, *args, **kwargs)

        joined = " ".join(map(str, cmd))
        src_match = _YOSYS_SRC_RE.search(joined)
        out_match = _YOSYS_OUT_RE.search(joined)
        if not (src_match and out_match):
            return real_run(cmd, *args, **kwargs)

        src = Path(src_match.group(1))
        out = Path(out_match.group(1))
        if not src.exists():
            return real_run(cmd, *args, **kwargs)

        key = hashlib.sha256(src.read_bytes()).hexdigest()
        if key in _yosys_json_cache:
            out.write_bytes(_yosys_json_cache[key])
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

        result = real_run(cmd, *args, **kwargs)
        if result.returncode == 0 and out.exists():
            _yosys_json_cache[key] = out.read_bytes()
        return result

    monkeypatch.setattr(subprocess, "run", cached_run)


@pytest.fixture
def project_directories(tmp_path: Path) -> dict[str, Path]:
    """Fixture that creates test directories and .env files for project directory
    precedence tests."""
    user_provided_dir = tmp_path / "user_provided_project"
    env_var_dir = tmp_path / "env_var_project"
    project_dotenv_dir = tmp_path / "project_dotenv_project"
    global_dotenv_dir = tmp_path / "global_dotenv_project"
    default_dir = tmp_path / "default_project"

    for project_dir in [
        user_provided_dir,
        env_var_dir,
        project_dotenv_dir,
        global_dotenv_dir,
        default_dir,
    ]:
        project_dir.mkdir()
        (project_dir / ".FABulous").mkdir()
        env_file = project_dir / ".FABulous" / ".env"
        env_file.touch()

        models_pack_file = project_dir / "models_pack.v"
        models_pack_file.touch()
        set_key(env_file, "FAB_PROJ_LANG", "verilog")
        set_key(env_file, "FAB_PROJ_VERSION", "1.0.0")
        set_key(env_file, "FAB_MODELS_PACK", str(models_pack_file))
        set_key(env_file, "FAB_PROJ_DIR", str(project_dir))

    project_dotenv_file = tmp_path / "project_specific.env"
    project_dotenv_file.touch()
    set_key(project_dotenv_file, "FAB_PROJ_DIR", str(project_dotenv_dir))

    project_dotenv_fallback_file = tmp_path / "project_fallback.env"
    project_dotenv_fallback_file.touch()
    set_key(project_dotenv_fallback_file, "FAB_PROJ_LANG", "verilog")
    set_key(project_dotenv_fallback_file, "FAB_PROJ_DIR", str(default_dir))

    global_dotenv_file = tmp_path / "global.env"
    global_dotenv_file.touch()
    set_key(global_dotenv_file, "FAB_PROJ_DIR", str(global_dotenv_dir))

    return {
        "user_provided_dir": user_provided_dir,
        "env_var_dir": env_var_dir,
        "project_dotenv_dir": project_dotenv_dir,
        "global_dotenv_dir": global_dotenv_dir,
        "default_dir": default_dir,
        "project_dotenv_file": project_dotenv_file,
        "project_dotenv_fallback_file": project_dotenv_fallback_file,
        "global_dotenv_file": global_dotenv_file,
    }


@pytest.fixture
def simulation_mock(cli: FABulous_CLI, mocker: MockerFixture) -> None:
    """Prepare a CLI instance for simulation tests.

    Mocks subprocess.run, generates the fabric, creates the required design artifacts
    (.json, .fasm, .bin), and runs bitstream generation.
    """
    mocker.patch("subprocess.run", return_value=MOCK_COMPLETED_PROCESS)
    run_cmd(cli, "run_fab")

    user_design = cli.projectDir / "user_design"
    for suffix in (".json", ".fasm", ".bin"):
        (user_design / f"sequential_16bit_en{suffix}").touch()

    run_cmd(cli, "compile_design ./user_design/sequential_16bit_en.v")


def find_task_calls() -> list[list[str]]:
    """Return the command lists from subprocess calls that invoked ``task``.

    Must be called while ``subprocess.run`` is patched by ``simulation_mock``.
    """
    mock = subprocess.run  # already patched by simulation_mock
    assert hasattr(mock, "call_args_list"), "subprocess.run is not mocked"
    return [
        c.args[0]
        for c in mock.call_args_list
        if c.args and isinstance(c.args[0], list | tuple) and c.args[0][0] == "task"
    ]
