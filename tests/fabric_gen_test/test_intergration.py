"""Integration tests for FABulous fabric generation."""

import subprocess
import sys
from pathlib import Path
from subprocess import run

import pytest
from dotenv import unset_key


@pytest.fixture(autouse=True)
def _disable_pdk_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FAB_PDK", raising=False)
    monkeypatch.delenv("FAB_PDK_ROOT", raising=False)

    real_run = subprocess.run

    def scrubbing_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        result = real_run(*args, **kwargs)
        for env_file in tmp_path.rglob(".FABulous/.env"):
            unset_key(env_file, "FAB_PDK")
            unset_key(env_file, "FAB_PDK_ROOT")
        return result

    monkeypatch.setattr(sys.modules[__name__], "run", scrubbing_run)


@pytest.mark.slow
def test_run_verilog_simulation_CLI(tmp_path: Path) -> None:
    """Test running Verilog simulation via CLI."""
    project_dir = tmp_path / "demo"
    result = run(["FABulous", "-c", str(project_dir)])
    assert result.returncode == 0

    result = run(
        ["FABulous", str(project_dir), "-fs", "./demo/FABulous.tcl"], cwd=tmp_path
    )
    assert result.returncode == 0


@pytest.mark.slow
def test_run_verilog_simulation_makefile(tmp_path: Path) -> None:
    """Test running Verilog simulation via Makefile."""
    project_dir = tmp_path / "demo"
    result = run(["FABulous", "-c", str(project_dir)])
    assert result.returncode == 0

    result = run(["task"], cwd=project_dir / "Test")
    assert result.returncode == 0


@pytest.mark.slow
def test_run_vhdl_simulation_makefile(tmp_path: Path) -> None:
    """Test running VHDL simulation via Makefile."""
    project_dir = tmp_path / "demo_vhdl"
    result = run(["FABulous", "-c", str(project_dir), "-w", "vhdl"])
    assert result.returncode == 0

    result = run(["task"], cwd=project_dir / "Test")
    assert result.returncode == 0
