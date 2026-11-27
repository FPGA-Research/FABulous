"""End-to-end tests of the documented ways to install FABulous.

Each test installs a wheel built from this checkout into an empty home
directory, the way a user installs from PyPI, and runs what it installed.
They download dependencies, so they are marked slow.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(
    argv: list[str], env: dict[str, str], stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `argv` in `env` and return the finished process."""
    return subprocess.run(
        argv,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


@pytest.fixture(scope="session")
def uv() -> str:
    """The `uv` executable."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    return uv


@pytest.fixture(scope="session")
def wheel(uv: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A FABulous wheel built from this checkout."""
    out_dir = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(out_dir), str(REPO_ROOT)],
        check=True,
        capture_output=True,
        timeout=900,
    )
    (wheel,) = out_dir.glob("*.whl")
    return wheel


@pytest.fixture
def fresh_home(tmp_path: Path, uv: str) -> dict[str, str]:
    """An environment with an empty home directory, like a new container.

    The uv cache and managed Pythons stay where they are, so packages and
    interpreters are not downloaded again for every test.
    """
    home = tmp_path / "home"
    home.mkdir()
    shared = {
        "UV_CACHE_DIR": run([uv, "cache", "dir"], dict(os.environ)).stdout.strip(),
        "UV_PYTHON_INSTALL_DIR": run(
            [uv, "python", "dir"], dict(os.environ)
        ).stdout.strip(),
    }
    return {
        "HOME": str(home),
        # `uv` is called by its full path: its directory may be a development
        # virtualenv that already has `task`.
        "PATH": os.pathsep.join([str(home / ".local" / "bin"), "/usr/bin", "/bin"]),
        "SHELL": "/bin/bash",
        "TERM": "dumb",
        "UV_NO_CONFIG": "1",
        **shared,
    }


def test_documented_uv_tool_install_puts_bundled_binaries_on_path(
    uv: str, wheel: Path, fresh_home: dict[str, str]
) -> None:
    result = run(
        [
            uv,
            "tool",
            "install",
            "--managed-python",
            "--with-executables-from",
            "go-task-bin,fabulous-bit-gen",
            str(wheel),
        ],
        fresh_home,
    )
    assert result.returncode == 0, result.stderr

    version = run(["FABulous", "--version"], fresh_home)
    assert version.returncode == 0, version.stderr
    assert "FABulous CLI" in version.stdout

    bin_dir = Path(fresh_home["HOME"]) / ".local" / "bin"
    for name in ("task", "bit_gen"):
        assert shutil.which(name, path=fresh_home["PATH"]) == str(bin_dir / name)
    assert "+pypi" in run(["task", "--version"], fresh_home).stdout


def test_python_without_tkinter_names_the_fix(
    uv: str, wheel: Path, fresh_home: dict[str, str]
) -> None:
    python = run([uv, "python", "find", "--no-managed-python", ">=3.12"], fresh_home)
    if python.returncode != 0:
        pytest.skip("no system Python 3.12 or newer")
    system_python = python.stdout.strip()
    if run([system_python, "-c", "import tkinter"], fresh_home).returncode == 0:
        pytest.skip(f"{system_python} has tkinter")

    result = run(
        [uv, "tool", "install", "--python", system_python, str(wheel)], fresh_home
    )
    assert result.returncode == 0, result.stderr
    version = run(["FABulous", "--version"], fresh_home)

    assert version.returncode != 0
    assert "--managed-python" in version.stderr
