"""Test FABulousSettings class."""

import os
from collections.abc import Generator
from importlib.metadata import version as meta_version
from pathlib import Path

import pytest
from dotenv import set_key
from packaging.version import Version
from pydantic import ValidationError
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_settings import (
    MODELS_PACK_REQUIRED_MODULES,
    FABulousSettings,
    get_context,
    init_context,
    reset_context,
)


@pytest.fixture(autouse=True)
def reset_context_before_and_after_tests() -> Generator:
    """Reset context before and after each test to ensure isolation."""
    reset_context()
    yield
    reset_context()


class TestFABulousSettings:
    """Test cases for FABulousSettings class."""

    def test_default_initialization(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        project: Path,
    ) -> None:
        """Test FABulousSettings initialization with clean state."""
        # Clear all FAB_ environment variables
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Remove the project .env file written by create_project to test defaults
        (project / ".FABulous" / ".env").unlink()

        # No tool on PATH: every tool path falls back to its executable name
        mocker.patch("fabulous.fabulous_settings.which", return_value=None)

        settings = init_context(project)

        assert {
            "yosys": settings.yosys_path,
            "sta": settings.opensta_path,
            "nextpnr-generic": settings.nextpnr_path,
            "iverilog": settings.iverilog_path,
            "vvp": settings.vvp_path,
            "ghdl": settings.ghdl_path,
            "klayout": settings.klayout_path,
            "openroad": settings.openroad_path,
        } == {
            "yosys": "yosys",
            "sta": "sta",
            "nextpnr-generic": "nextpnr-generic",
            "iverilog": "iverilog",
            "vvp": "vvp",
            "ghdl": "ghdl",
            "klayout": "klayout",
            "openroad": "openroad",
        }
        assert settings.proj_dir == project
        assert settings.fabulator_root is None
        assert settings.oss_cad_suite is None
        assert settings.proj_version_created == Version("0.0.1")
        assert settings.proj_version == Version(meta_version("FABulous-FPGA"))
        assert settings.proj_lang is HDLType.VERILOG
        # With no FAB_MODELS_PACK, a Verilog project's pack is guessed.
        assert settings.models_pack == project / "Fabric" / "models_pack.v"
        assert settings.max_worker == 2
        assert settings.switch_matrix_debug_signal is False
        assert settings.pdk is None
        assert settings.pdk_root is None
        assert settings.pdk_hash is None

    def test_initialization_with_environment_variables(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test FABulousSettings initialization with environment variables."""
        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        monkeypatch.setenv("FAB_PROJ_DIR", str(project))
        monkeypatch.setenv("FAB_PROJ_LANG", "vhdl")
        monkeypatch.setenv("FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")
        monkeypatch.setenv("FAB_PROJ_VERSION_CREATED", "1.2.3")
        (project / "my_models_pack.vhdl").touch()
        monkeypatch.setenv("FAB_MODELS_PACK", str(project / "my_models_pack.vhdl"))

        # Mock which to return None (no tools found)
        mocker.patch("fabulous.fabulous_settings.which", return_value=None)

        settings = init_context()

        assert settings.proj_dir == project
        assert settings.proj_lang is HDLType.VHDL
        assert settings.models_pack == project / "my_models_pack.vhdl"
        assert settings.switch_matrix_debug_signal is True
        assert settings.proj_version_created == Version("1.2.3")

    @pytest.mark.parametrize("max_worker", [0, 4])
    def test_max_worker_non_negative_accepted(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        max_worker: int,
    ) -> None:
        """FAB_MAX_WORKER >= 0 is kept as given (the pool maps 0 to the default)."""
        monkeypatch.setenv("FAB_MAX_WORKER", str(max_worker))
        mocker.patch("fabulous.fabulous_settings.which", return_value=None)

        settings = init_context(project)

        assert settings.max_worker == max_worker

    def test_max_worker_negative_rejected(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """A negative FAB_MAX_WORKER fails validation rather than being normalised."""
        monkeypatch.setenv("FAB_MAX_WORKER", "-1")
        mocker.patch("fabulous.fabulous_settings.which", return_value=None)

        with pytest.raises(ValidationError, match="max_worker"):
            init_context(project)

    def test_initialization_with_tool_paths_found(
        self, project: Path, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Every tool path field resolves its own executable through `which`."""
        # Each tool resolves to a distinct directory, so a field looking up the
        # wrong executable name lands on the wrong path.
        tool_bin = tmp_path / "bin"
        mocker.patch(
            "fabulous.fabulous_settings.which",
            side_effect=lambda tool: str(tool_bin / tool / tool),
        )

        settings = init_context(project)

        assert {
            "yosys_path": settings.yosys_path,
            "opensta_path": settings.opensta_path,
            "nextpnr_path": settings.nextpnr_path,
            "iverilog_path": settings.iverilog_path,
            "vvp_path": settings.vvp_path,
            "ghdl_path": settings.ghdl_path,
            "klayout_path": settings.klayout_path,
            "openroad_path": settings.openroad_path,
        } == {
            "yosys_path": tool_bin / "yosys" / "yosys",
            "opensta_path": tool_bin / "sta" / "sta",
            "nextpnr_path": tool_bin / "nextpnr-generic" / "nextpnr-generic",
            "iverilog_path": tool_bin / "iverilog" / "iverilog",
            "vvp_path": tool_bin / "vvp" / "vvp",
            "ghdl_path": tool_bin / "ghdl" / "ghdl",
            "klayout_path": tool_bin / "klayout" / "klayout",
            "openroad_path": tool_bin / "openroad" / "openroad",
        }

    def test_initialization_with_explicit_tool_paths(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test FABulousSettings initialization with explicitly set tool paths."""
        # Clear all FAB_ environment variables first
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        yosys_path = tmp_path / "yosys"
        nextpnr_path = tmp_path / "nextpnr-generic"
        yosys_path.touch()
        nextpnr_path.touch()

        monkeypatch.setenv("FAB_YOSYS_PATH", str(yosys_path))
        monkeypatch.setenv("FAB_NEXTPNR_PATH", str(nextpnr_path))

        mocker.patch("fabulous.fabulous_settings.which", return_value=None)
        settings = init_context(project)

        assert settings.yosys_path == Path(yosys_path)
        assert settings.nextpnr_path == Path(nextpnr_path)
        # Tools not explicitly set should still be resolved via which
        assert settings.iverilog_path == "iverilog"
        assert settings.vvp_path == "vvp"

    def test_initialization_with_no_init_called(self, mocker: MockerFixture) -> None:
        """Without init_context, get_context builds an unvalidated API-mode context."""
        mock_which = mocker.patch("fabulous.fabulous_settings.which")
        settings = get_context()

        # No validator runs: tools are not looked up and the cwd, which is not
        # a FABulous project, is accepted as the project directory.
        mock_which.assert_not_called()
        assert settings.yosys_path == "yosys"
        assert settings.nextpnr_path == "nextpnr-generic"
        assert settings.proj_dir == Path.cwd()
        assert not (Path.cwd() / ".FABulous").exists()

    @pytest.mark.parametrize(
        ("configured_pdk", "expected_pdk"),
        [
            ("sky130", "sky130A"),
            ("sky130B", "sky130B"),
            ("sky130A", "sky130A"),
            ("ihp-sg13", "ihp-sg13g2"),
            ("ihp-sg13g2", "ihp-sg13g2"),
            ("ihp-sg13cmos5l", "ihp-sg13cmos5l"),
            ("gf180mcu", "gf180mcuD"),
        ],
    )
    def test_pdk_variant_resolution(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        tmp_path: Path,
        configured_pdk: str,
        expected_pdk: str,
    ) -> None:
        """FAB_PDK family names auto-resolve to default variant; variants stay."""
        pdk_root = tmp_path / "pdk_root"
        pdk_root.mkdir()
        monkeypatch.setenv("FAB_PDK", configured_pdk)
        monkeypatch.setenv("FAB_PDK_ROOT", str(pdk_root))
        monkeypatch.setenv("FAB_PDK_HASH", "deadbeef" * 5)

        mocker.patch("fabulous.fabulous_settings.which", return_value=None)
        mocker.patch(
            "librelane.common.misc.get_ciel_pdk_hash", return_value="deadbeef" * 5
        )
        mocker.patch("ciel.manage.enable")

        settings = init_context(project)
        assert settings.pdk == expected_pdk


class TestFieldValidators:
    """Field validators, exercised through real `FABulousSettings` validation."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param("verilog", HDLType.VERILOG, id="verilog"),
            pytest.param("VHDL", HDLType.VHDL, id="upper_case"),
            pytest.param(" System_Verilog ", HDLType.SYSTEM_VERILOG, id="padded"),
            pytest.param(HDLType.VHDL, HDLType.VHDL, id="enum"),
            pytest.param("v", HDLType.VERILOG, id="alias_v"),
            pytest.param("sv", HDLType.SYSTEM_VERILOG, id="alias_sv"),
            pytest.param("vhd", HDLType.VHDL, id="alias_vhd"),
        ],
    )
    def test_proj_lang_normalised(
        self, project: Path, value: str | HDLType, expected: HDLType
    ) -> None:
        """The project language is case- and whitespace-insensitive."""
        settings = FABulousSettings(proj_dir=project, proj_lang=value)
        assert settings.proj_lang is expected

    def test_proj_lang_invalid_rejected(self, project: Path) -> None:
        """An unknown project language fails validation."""
        with pytest.raises(ValidationError, match="proj_lang"):
            FABulousSettings(proj_dir=project, proj_lang="python")

    @pytest.mark.parametrize("exists", [False, True], ids=["created", "existing"])
    def test_user_config_dir_is_created(
        self, project: Path, tmp_path: Path, exists: bool
    ) -> None:
        """The user config directory is created, parents included, when missing."""
        config_dir = tmp_path / "config" / "nested"
        if exists:
            config_dir.mkdir(parents=True)

        settings = FABulousSettings(proj_dir=project, user_config_dir=config_dir)

        assert settings.user_config_dir == config_dir
        assert config_dir.is_dir()

    def test_proj_dir_is_resolved(self, project: Path) -> None:
        """A project directory given through `..` is stored resolved."""
        settings = FABulousSettings(proj_dir=project / ".." / project.name)
        assert settings.proj_dir == project.resolve()

    def test_proj_dir_without_fabulous_directory_rejected(self, tmp_path: Path) -> None:
        """A directory without `.FABulous` is not a FABulous project."""
        project_dir = tmp_path / "invalid_project"
        project_dir.mkdir()

        with pytest.raises(ValidationError, match="is not a FABulous project"):
            FABulousSettings(proj_dir=project_dir)

    def test_explicit_tool_path_object_kept_without_lookup(
        self, project: Path, mocker: MockerFixture
    ) -> None:
        """A `Path` tool value is kept as given and never looked up on PATH."""
        mock_which = mocker.patch("fabulous.fabulous_settings.which", return_value=None)

        settings = FABulousSettings(
            proj_dir=project, yosys_path=Path("/custom/tool/path")
        )

        assert settings.yosys_path == Path("/custom/tool/path")
        assert mocker.call("yosys") not in mock_which.call_args_list


class TestModelsPackValidation:
    """Tests for models-pack definition presence checks."""

    @pytest.mark.parametrize(
        ("lang", "file_name", "content", "expected_missing"),
        [
            pytest.param(
                "verilog",
                "models_pack_incomplete.v",
                "module config_latch(); endmodule\n"
                "module my_buf(); endmodule\n"
                "// module clk_buf(); endmodule\n"
                "/*\nmodule cus_mux41(); endmodule\n*/\n",
                ["clk_buf", "cus_mux41", "cus_mux21", "cus_mux81", "cus_mux161"],
                id="verilog_commented_out_modules_missing",
            ),
            pytest.param(
                "vhdl",
                "my_lib_incomplete.vhdl",
                "entity CONFIG_LATCH is\n"
                "end entity CONFIG_LATCH;\n"
                "entity MY_BUF is\n"
                "end entity MY_BUF;\n"
                "-- entity CLK_BUF is\n"
                "-- end entity CLK_BUF;\n",
                ["clk_buf", "cus_mux41", "cus_mux21", "cus_mux81", "cus_mux161"],
                id="vhdl_entities_matched_case_insensitively",
            ),
            pytest.param(
                "verilog",
                "models_pack_complete.v",
                "".join(
                    f"module {module_name}(); endmodule\n"
                    for module_name in MODELS_PACK_REQUIRED_MODULES
                ),
                [],
                id="verilog_complete",
            ),
        ],
    )
    def test_missing_definitions_warning(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
        lang: str,
        file_name: str,
        content: str,
        expected_missing: list[str],
    ) -> None:
        """Warn with exactly the required definitions a models pack lacks."""
        mocker.patch("fabulous.fabulous_settings.which", return_value=None)
        models_pack = project / "Fabric" / file_name
        models_pack.write_text(content)
        monkeypatch.setenv("FAB_PROJ_LANG", lang)
        monkeypatch.setenv("FAB_MODELS_PACK", str(models_pack))

        settings = init_context(project)

        assert settings.models_pack == models_pack
        messages = [r.message for r in caplog.records]
        # Proves the validator ran and was captured, so an empty warning list
        # below is not vacuous.
        assert f"Using models pack at: {models_pack}" in messages
        expected_warnings = (
            [
                f"The models pack at '{models_pack}' is missing the following "
                f"models-pack definitions: {expected_missing}. "
                "The models pack may be outdated. Update it to a recent "
                "version from upstream FABulous, or use an older version "
                "of FABulous."
            ]
            if expected_missing
            else []
        )
        assert [m for m in messages if "missing the following" in m] == (
            expected_warnings
        )


class TestContextMethods:
    """Test cases for the new context management methods."""

    def test_init_context_basic(self, project: Path, tmp_path: Path) -> None:
        """A fresh project resolves its own `.FABulous/.env` settings."""
        settings = init_context(project_dir=project)

        assert settings.proj_dir == project
        assert settings.proj_lang is HDLType.VERILOG
        assert settings.proj_version_created == Version(meta_version("FABulous-FPGA"))
        # The .env stores "../Fabric/models_pack.v", relative to .FABulous.
        assert settings.models_pack == project / "Fabric" / "models_pack.v"
        # A ciel family PDK without FAB_PDK_ROOT is rooted in the ciel home,
        # which the autouse test environment points at tmp_path/.ciel.
        assert settings.pdk == "ihp-sg13g2"
        assert settings.pdk_root == tmp_path / ".ciel" / "ihp-sg13"

    def test_init_context_with_global_env_file(
        self, project: Path, tmp_path: Path
    ) -> None:
        """Test context initialization with global .env file."""
        # Remove the project's default .env file to test global .env file precedence
        project_env = project / ".FABulous" / ".env"
        if project_env.exists():
            project_env.unlink()

        # Create global .env file
        global_env = tmp_path / "global.env"
        global_env.touch()
        set_key(global_env, "FAB_PROJ_LANG", "vhdl")
        set_key(global_env, "FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")

        settings = init_context(project_dir=project, global_dot_env=global_env)

        assert settings.proj_lang == "vhdl"
        assert settings.switch_matrix_debug_signal is True

    def test_init_context_with_project_env_file(
        self, project: Path, tmp_path: Path
    ) -> None:
        """An explicit project .env overrides the project's own `.FABulous/.env`."""
        project_env = tmp_path / "project.env"
        project_env.touch()
        set_key(project_env, "FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")
        # .FABulous/.env also sets this one, to the installed FABulous version.
        set_key(project_env, "FAB_PROJ_VERSION_CREATED", "9.9.9")

        settings = init_context(project_dir=project, project_dot_env=project_env)

        assert settings.switch_matrix_debug_signal is True
        assert settings.proj_version_created == Version("9.9.9")

    def test_init_context_env_file_precedence(
        self, project: Path, tmp_path: Path
    ) -> None:
        """Test that project .env file overrides global .env file."""
        # Remove the project's default .env file to test precedence properly
        project_default_env = project / ".FABulous" / ".env"
        if project_default_env.exists():
            project_default_env.unlink()

        # Create global .env file
        global_env = tmp_path / "global.env"
        global_env.touch()
        set_key(global_env, "FAB_PROJ_LANG", "vhdl")
        set_key(global_env, "FAB_PROJ_VERSION_CREATED", "1.0.0")

        # Create project .env file that overrides language
        project_env = tmp_path / "project.env"
        project_env.touch()
        set_key(project_env, "FAB_PROJ_LANG", "verilog")
        set_key(project_env, "FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")

        settings = init_context(
            project_dir=project,
            global_dot_env=global_env,
            project_dot_env=project_env,
        )

        # Project .env should override global .env for PROJ_LANG
        assert settings.proj_lang == "verilog"
        # But global .env values should still be loaded where not overridden
        assert settings.proj_version_created == Version("1.0.0")
        assert settings.switch_matrix_debug_signal is True

    def test_init_context_auto_env_file_discovery(self, project: Path) -> None:
        """Test automatic discovery of .env files in standard locations."""
        # Create .env file in .FABulous directory
        fabulous_env = project / ".FABulous" / ".env"
        fabulous_env.touch()
        set_key(fabulous_env, "FAB_PROJ_LANG", "system_verilog")

        settings = init_context(project_dir=project)

        # .env file should be loaded
        assert settings.proj_lang == "system_verilog"  # From fabulous .env

    def test_init_context_missing_env_file_warning(
        self, project: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A missing explicit global .env file is warned about, then ignored."""
        nonexistent_env = tmp_path / "nonexistent.env"

        settings = init_context(project_dir=project, global_dot_env=nonexistent_env)

        assert (
            f"Explicit Global .env file: {nonexistent_env} is provided, "
            "but this is not found, this entry is ignored" in caplog.text
        )
        assert settings.proj_dir == project

    def test_init_context_overwrites_existing(
        self, project: Path, tmp_path: Path
    ) -> None:
        """Test that subsequent init_context calls overwrite the existing context."""
        project_dir2 = tmp_path / "project2"
        project_dir2.mkdir()
        (project_dir2 / ".FABulous").mkdir()

        # First initialization
        init_context(project_dir=project)
        context1 = get_context()
        assert context1.proj_dir == project

        # Second initialization should overwrite
        init_context(project_dir=project_dir2)
        context2 = get_context()
        assert context2.proj_dir == project_dir2
        assert context1 is not context2  # Different instances

    def test_get_context_after_init(self, project: Path) -> None:
        """Test getting context after initialization."""
        init_settings = init_context(project_dir=project)
        retrieved_settings = get_context()

        assert init_settings is retrieved_settings
        assert retrieved_settings.proj_dir == project

    def test_reset_context(self, project: Path) -> None:
        """Test context reset functionality."""
        # Initialize context
        init_context(project_dir=project)
        settings = get_context()
        assert settings.proj_dir == project

        # Reset context
        reset_context()

        # Should raise error after reset
        from fabulous.fabulous_settings import _context_instance

        assert _context_instance is None

    def test_init_context_with_env_var_overrides(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variables override .env values; other .env values apply."""
        # Neither key is set by the project's own .FABulous/.env, which would
        # otherwise outrank the global .env and hide the override.
        env_file = tmp_path / "test.env"
        env_file.touch()
        set_key(env_file, "FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "false")
        set_key(env_file, "FAB_MAX_WORKER", "7")
        monkeypatch.setenv("FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")

        settings = init_context(project_dir=project, global_dot_env=env_file)

        assert settings.switch_matrix_debug_signal is True
        assert settings.max_worker == 7

    def test_context_with_invalid_env_file_values(
        self, project: Path, tmp_path: Path
    ) -> None:
        """Test context initialization with invalid values in .env files."""
        # Remove the project's default .env file so our invalid
        # .env file takes precedence
        project_default_env = project / ".FABulous" / ".env"
        if project_default_env.exists():
            project_default_env.unlink()

        # Create .env with invalid project language
        env_file = tmp_path / "invalid.env"
        env_file.touch()
        set_key(env_file, "FAB_PROJ_LANG", "invalid_language")

        with pytest.raises(ValidationError, match="validation error"):
            init_context(project_dir=project, global_dot_env=env_file)

    def test_context_preserves_working_directory(self, project: Path) -> None:
        """Test that context initialization doesn't change working directory."""
        original_cwd = Path.cwd()

        init_context(project_dir=project)

        # Working directory should be unchanged
        assert Path.cwd() == original_cwd

    def test_init_context_with_fab_proj_dir_env_var(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test context initialization with FAB_PROJ_DIR environment variable."""
        # Set environment variable
        monkeypatch.setenv("FAB_PROJ_DIR", str(project))

        settings = init_context()

        # Should use the environment variable for project directory
        assert settings.proj_dir == project

    def test_init_context_project_dir_overrides_env_var(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that explicit project_dir parameter overrides FAB_PROJ_DIR env var."""
        env_project_dir = tmp_path / "env_project"
        env_project_dir.mkdir()
        (env_project_dir / ".FABulous").mkdir()

        # Set environment variable
        monkeypatch.setenv("FAB_PROJ_DIR", str(env_project_dir))

        settings = init_context(project_dir=project)

        # The explicit project_dir parameter should override the env var
        assert settings.proj_dir == project

    def test_context_integration_with_real_project_structure(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test context initialization with realistic project structure."""
        # Create global .env file with typical settings
        global_env = tmp_path / "global.env"
        global_env.touch()
        set_key(global_env, "FAB_YOSYS_PATH", str(tmp_path / "yosys"))
        set_key(global_env, "FAB_OSS_CAD_SUITE", str(tmp_path / "oss-cad-suite"))
        (tmp_path / "yosys").touch()

        project_env = project / ".FABulous" / ".env"
        project_env.touch()
        set_key(project_env, "FAB_PROJ_LANG", "verilog")
        set_key(project_env, "FAB_PROJ_VERSION_CREATED", "1.0.0")

        # Clean environment and set required vars
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("FAB_PROJ_DIR", str(project))

        settings = init_context(project_dir=project, global_dot_env=global_env)

        assert settings.proj_dir == project
        assert settings.proj_lang == "verilog"
        assert settings.proj_version_created == Version("1.0.0")
        assert str(settings.yosys_path) == str(tmp_path / "yosys")


class TestCheckPdkAutoResolution:
    """Test cases for PDK auto-resolution in check_pdk validator."""

    @staticmethod
    def _clear_project_env_file(project: Path) -> None:
        """Remove project .env file so pydantic-settings doesn't load stale values."""
        env_file = project / ".FABulous" / ".env"
        if env_file.exists():
            env_file.unlink()

    def _setup_pdk_env(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        *,
        pdk_name: str = "ihp-sg13g2",
        pdk_root: Path | None = None,
        set_pdk_env: bool = True,
        set_pdk_root_env: bool = True,
        mock_ciel_enable: bool = True,
    ) -> Path | None:
        """Common setup: clear FAB_ env vars, clean .env file, mock which.

        Parameters
        ----------
        project : Path
            Project directory path.
        monkeypatch : pytest.MonkeyPatch
            Pytest monkeypatch fixture for environment manipulation.
        mocker : MockerFixture
            Pytest-mock mocker fixture.
        pdk_name : str
            PDK family name (used for env var and default pdk_root path).
        pdk_root : Path | None
            Explicit pdk_root path. When None and ``set_pdk_root_env`` is True,
            a default path under ``project.parent / ".ciel"`` is created.
        set_pdk_env : bool
            When True (default), set ``FAB_PDK`` env var.
        set_pdk_root_env : bool
            When True (default), set ``FAB_PDK_ROOT`` env var and create the dir.
        mock_ciel_enable : bool
            When True (default), mock ``ciel.manage.enable`` so tests don't
            make real network calls.

        Returns
        -------
        Path | None
            The pdk_root path if set_pdk_root_env is True, otherwise None.
        """
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        self._clear_project_env_file(project)

        mocker.patch("fabulous.fabulous_settings.which", return_value=None)

        if mock_ciel_enable:
            mocker.patch("ciel.manage.enable")

        if set_pdk_root_env:
            if pdk_root is None:
                pdk_root = project.parent / ".ciel" / pdk_name
            pdk_root.mkdir(parents=True, exist_ok=True)
            monkeypatch.setenv("FAB_PDK_ROOT", str(pdk_root))

        if set_pdk_env:
            monkeypatch.setenv("FAB_PDK", pdk_name)

        return pdk_root

    @pytest.mark.parametrize(
        ("configured_hash", "recommended_hash", "expect_mismatch_warning"),
        [
            ("user_hash_789aaa", "recommended_hash_456", True),
            ("matching_hash_xyz", "matching_hash_xyz", False),
        ],
        ids=["mismatched_hash_warns", "matching_hash_no_warning"],
    )
    def test_hash_warning_behavior(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
        configured_hash: str,
        recommended_hash: str,
        expect_mismatch_warning: bool,
    ) -> None:
        """Test warning behavior for configured vs recommended pdk hash."""
        self._setup_pdk_env(project, monkeypatch, mocker)
        mocker.patch(
            "librelane.common.misc.get_ciel_pdk_hash",
            return_value=recommended_hash,
        )
        monkeypatch.setenv("FAB_PDK_HASH", configured_hash)

        settings = init_context(project)
        assert settings.pdk_hash == configured_hash
        has_mismatch_warning = any(
            "PDK hash mismatch" in r.message for r in caplog.records
        )
        assert has_mismatch_warning is expect_mismatch_warning

    def test_error_from_get_ciel_pdk_hash_propagates(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """A family with no librelane-validated PDK hash fails settings validation."""
        self._setup_pdk_env(project, monkeypatch, mocker)
        mocker.patch(
            "librelane.common.misc.get_ciel_pdk_hash",
            side_effect=ValueError("no validated version"),
        )

        with pytest.raises(ValidationError, match="no validated version"):
            init_context(project)

    @pytest.mark.parametrize(
        ("pdk_name", "expected_family"),
        [
            ("sky130", "sky130"),
            ("gf180mcu", "gf180mcu"),
            ("ihp-sg13", "ihp-sg13"),
            ("ihp-sg13g2", "ihp-sg13"),
            ("ihp-sg13cmos5l", "ihp-sg13"),
            ("custom_unknown_pdk", None),
        ],
    )
    def test_pdk_resolution_by_family(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        pdk_name: str,
        expected_family: str | None,
    ) -> None:
        """A variant resolves to its ciel family; unknown PDKs skip resolution."""
        is_known_family = expected_family is not None
        pdk_root = None if is_known_family else project.parent / "custom_pdk"
        self._setup_pdk_env(
            project,
            monkeypatch,
            mocker,
            pdk_name=pdk_name,
            pdk_root=pdk_root,
            mock_ciel_enable=False,
        )
        expected_hash = f"hash_for_{pdk_name}_abc123"
        mock_get_hash = mocker.patch(
            "librelane.common.misc.get_ciel_pdk_hash",
            return_value=expected_hash,
        )
        mock_enable = mocker.patch("ciel.manage.enable")

        settings = init_context(project)

        if is_known_family:
            assert settings.pdk_hash == expected_hash
            mock_enable.assert_called_once()
            call_kwargs = mock_enable.call_args[1]
            assert call_kwargs["pdk"] == expected_family
            assert call_kwargs["version"] == expected_hash
        else:
            assert settings.pdk_hash is None
            mock_get_hash.assert_not_called()
            mock_enable.assert_not_called()

    def test_ciel_enable_failure_raises(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that ciel.manage.enable errors propagate as ValueError."""
        self._setup_pdk_env(
            project,
            monkeypatch,
            mocker,
            mock_ciel_enable=False,
        )
        mocker.patch(
            "librelane.common.misc.get_ciel_pdk_hash",
            return_value="bad_hash_no_manifest",
        )
        mocker.patch(
            "ciel.manage.enable",
            side_effect=ValueError("Manifest not found"),
        )

        with pytest.raises(ValueError, match="Manifest not found"):
            init_context(project)

    def test_pdk_path_not_exists_raises(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that a non-existent pdk_path raises ValueError after enable."""
        pdk_root = project.parent / "nonexistent_pdk_root"
        self._setup_pdk_env(project, monkeypatch, mocker, pdk_root=pdk_root)
        mocker.patch(
            "librelane.common.misc.get_ciel_pdk_hash",
            return_value="some_hash_abc",
        )
        # _setup_pdk_env creates pdk_root; remove it so the exists() check fails
        pdk_root.rmdir()

        with pytest.raises(ValueError, match="does not exist"):
            init_context(project)

    def test_auto_resolve_pdk_root_from_ciel_home(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test pdk_root auto-resolved from ciel home when pdk is a ciel family."""
        self._setup_pdk_env(
            project,
            monkeypatch,
            mocker,
            set_pdk_root_env=False,
        )

        ciel_home = tmp_path / "ciel_home"
        ciel_home.mkdir()
        # Simulate the directory that ciel.manage.enable would create
        (ciel_home / "ihp-sg13").mkdir()
        mocker.patch(
            "fabulous.fabulous_settings.get_ciel_home",
            return_value=str(ciel_home),
        )
        mocker.patch(
            "librelane.common.misc.get_ciel_pdk_hash",
            return_value="auto_hash",
        )

        settings = init_context(project)
        assert settings.pdk_root == ciel_home / "ihp-sg13"
        assert settings.pdk_hash == "auto_hash"

    @pytest.mark.parametrize(
        ("set_pdk_env", "set_pdk_root_env", "pdk_name", "expected_match"),
        [
            pytest.param(
                True,
                False,
                "custom_unknown_pdk",
                "is not supported by ciel and FAB_PDK_ROOT is not set",
                id="pdk_without_root",
            ),
            pytest.param(
                False,
                True,
                "ihp-sg13g2",
                "FAB_PDK_ROOT is set but FAB_PDK is not",
                id="root_without_pdk",
            ),
        ],
    )
    def test_incomplete_pdk_config_raises(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        tmp_path: Path,
        set_pdk_env: bool,
        set_pdk_root_env: bool,
        pdk_name: str,
        expected_match: str,
    ) -> None:
        """Test that setting only one of FAB_PDK / FAB_PDK_ROOT raises.

        Covers two incomplete-configuration scenarios:
        - PDK name set without a root path  -> expects error mentioning FAB_PDK_ROOT
        - PDK root set without a PDK name   -> expects error mentioning FAB_PDK
        """
        pdk_root = tmp_path / "some_pdk" if set_pdk_root_env else None
        self._setup_pdk_env(
            project,
            monkeypatch,
            mocker,
            pdk_name=pdk_name,
            pdk_root=pdk_root,
            set_pdk_env=set_pdk_env,
            set_pdk_root_env=set_pdk_root_env,
        )

        with pytest.raises(ValidationError, match=expected_match):
            init_context(project)

    def test_both_pdk_and_root_none_warns(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test warning when both pdk and pdk_root are None."""
        self._setup_pdk_env(
            project,
            monkeypatch,
            mocker,
            set_pdk_env=False,
            set_pdk_root_env=False,
        )

        settings = init_context(project)
        assert settings.pdk_root is None
        assert settings.pdk is None
        assert any("PDK_root or PDK is not set" in r.message for r in caplog.records)
