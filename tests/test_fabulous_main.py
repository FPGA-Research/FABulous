"""Test module for the FABulous nix-env command."""

import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabulous import NixShell, main


def make_flake_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with a fake flake.nix."""
    flake_dir = tmp_path / "nix_flake"
    flake_dir.mkdir()
    (flake_dir / "flake.nix").write_text("{ }")
    return flake_dir


# ---------------------------------------------------------------------------
# Error paths: nix not installed, flake missing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("has_nix", "has_flake"),
    [
        pytest.param(False, True, id="nix-not-installed"),
        pytest.param(True, False, id="flake-missing"),
    ],
)
def test_nix_env_error_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    has_nix: bool,
    has_flake: bool,
) -> None:
    flake_dir = tmp_path / "flake_dir"
    flake_dir.mkdir()
    if has_flake:
        (flake_dir / "flake.nix").write_text("{ }")

    mocker.patch(
        "shutil.which",
        return_value="/nix/store/fake/bin/nix" if has_nix else None,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["FABulous", "nix-env", "--flake-dir", str(flake_dir)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Flake directory auto-discovery
# ---------------------------------------------------------------------------


def test_flake_dir_auto_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    # Simulate packaged nix assets via importlib.resources.files("fabulous_nix")
    resource_dir = tmp_path / "site-packages" / "fabulous_nix"
    resource_dir.mkdir(parents=True)
    (resource_dir / "flake.nix").write_text("{ }")
    mocker.patch("importlib.resources.files", return_value=resource_dir)
    expected_path = str(resource_dir)

    mocker.patch("shutil.which", return_value="/nix/store/fake/bin/nix")
    mock_execvpe = mocker.patch("os.execvpe")
    monkeypatch.setattr(sys, "argv", ["FABulous", "nix-env", "--shell", "bash"])

    with pytest.raises(SystemExit):
        main()

    mock_execvpe.assert_called_once()
    _, nix_argv, _ = mock_execvpe.call_args[0]
    flake_ref = nix_argv[2]
    assert flake_ref == f"path:{expected_path}#nix-env"


# ---------------------------------------------------------------------------
# Shell detection, flake fragment, and execvp structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shell_env", "shell_option", "expected_shell"),
    [
        pytest.param("/bin/bash", None, "bash", id="auto-bash"),
        pytest.param("/usr/bin/fish", None, "fish", id="auto-fish"),
        pytest.param("/bin/zsh", None, "zsh", id="auto-zsh"),
        pytest.param("/usr/bin/tcsh", None, "bash", id="auto-unsupported-fallback"),
        pytest.param("/bin/zsh", "bash", "bash", id="override-bash"),
        pytest.param("/bin/bash", "fish", "fish", id="override-fish"),
        pytest.param("/bin/bash", "zsh", "zsh", id="override-zsh"),
        pytest.param("/bin/bash", "FISH", "fish", id="case-insensitive"),
    ],
)
def test_nix_env_shell_and_execvp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    shell_env: str,
    shell_option: str | None,
    expected_shell: str,
) -> None:
    flake_dir = make_flake_dir(tmp_path)
    monkeypatch.delenv("FAB_NIX_SHELL", raising=False)
    monkeypatch.setenv("SHELL", shell_env)
    mocker.patch("shutil.which", return_value="/nix/store/fake/bin/nix")
    mock_execvpe = mocker.patch("os.execvpe")

    argv = ["FABulous", "nix-env", "--flake-dir", str(flake_dir)]
    if shell_option is not None:
        argv += ["--shell", shell_option]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit):
        main()

    mock_execvpe.assert_called_once()
    binary, nix_argv, env_vars = mock_execvpe.call_args[0]

    # Always uses the dedicated nix-env devshell (no --command,
    # shell exec happens inside shellHook to preserve PATH)
    assert binary == "nix"
    assert nix_argv == [
        "nix",
        "develop",
        f"path:{flake_dir.resolve()}#nix-env",
    ]
    # FAB_NIX_SHELL in exec environment tells shellHook which shell to exec into
    assert env_vars.get("FAB_NIX_SHELL") == expected_shell
    # --no-check not passed, so env var should be 0
    assert env_vars.get("FAB_NIX_NO_CHECK") == "0"


# ---------------------------------------------------------------------------
# --no-check flag
# ---------------------------------------------------------------------------


def test_nix_env_no_check_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    flake_dir = make_flake_dir(tmp_path)
    monkeypatch.delenv("FAB_NIX_SHELL", raising=False)
    monkeypatch.setenv("SHELL", "/bin/bash")
    mocker.patch("shutil.which", return_value="/nix/store/fake/bin/nix")
    mock_execvpe = mocker.patch("os.execvpe")
    monkeypatch.setattr(
        sys,
        "argv",
        ["FABulous", "nix-env", "--flake-dir", str(flake_dir), "--no-check"],
    )

    with pytest.raises(SystemExit):
        main()

    mock_execvpe.assert_called_once()
    _, _, env_vars = mock_execvpe.call_args[0]
    assert env_vars.get("FAB_NIX_NO_CHECK") == "1"


def test_nix_env_uses_settings_shell_when_not_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    flake_dir = make_flake_dir(tmp_path)
    monkeypatch.setenv("FAB_NIX_SHELL", "zsh")
    monkeypatch.setenv("SHELL", "/bin/bash")
    mocker.patch("shutil.which", return_value="/nix/store/fake/bin/nix")
    mock_execvpe = mocker.patch("os.execvpe")
    monkeypatch.setattr(sys, "argv", ["FABulous", "nix-env", "--flake-dir", str(flake_dir)])

    with pytest.raises(SystemExit):
        main()

    mock_execvpe.assert_called_once()
    _, _, env_vars = mock_execvpe.call_args[0]
    assert env_vars.get("FAB_NIX_SHELL") == "zsh"


# ---------------------------------------------------------------------------
# NixShell enum
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "member"),
    [
        pytest.param("bash", NixShell.BASH, id="bash"),
        pytest.param("fish", NixShell.FISH, id="fish"),
        pytest.param("zsh", NixShell.ZSH, id="zsh"),
    ],
)
def test_nix_shell_enum_from_string(value: str, member: NixShell) -> None:
    assert NixShell(value) == member


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("tcsh", id="tcsh"),
        pytest.param("csh", id="csh"),
        pytest.param("", id="empty"),
    ],
)
def test_nix_shell_enum_invalid(value: str) -> None:
    assert NixShell(value) is NixShell.BASH
