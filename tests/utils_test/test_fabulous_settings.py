"""Test FABulousSettings class."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from dotenv import set_key
from packaging.version import Version
from pydantic import ValidationError
from pytest_mock import MockerFixture

from fabulous.fabulous_settings import (
    FABulousSettings,
    get_context,
    init_context,
    reset_context,
)


@pytest.fixture(autouse=True)
def reset_context_before_and_after_tests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator:
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

        # Remove any existing project .env file to test defaults
        project_env = project / ".FABulous" / ".env"
        if project_env.exists():
            project_env.unlink()

        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        # Mock which to return None (no tools found)
        mocker.patch("fabulous.fabulous_settings.which", return_value=None)

        settings = init_context(project)

        # user_config_dir should be created and exist
        assert settings.user_config_dir.exists()
        assert settings.user_config_dir.is_dir()
        assert settings.yosys_path == "yosys"
        assert settings.nextpnr_path == "nextpnr-generic"
        assert settings.iverilog_path == "iverilog"
        assert settings.vvp_path == "vvp"
        assert settings.klayout_path == "klayout"
        assert settings.openroad_path == "openroad"
        assert settings.proj_dir == project
        assert settings.fabulator_root is None
        # Note: oss_cad_suite might be set from previous tests or environment
        assert isinstance(settings.proj_version_created, Version)
        assert settings.proj_version_created == Version("0.0.1")  # Default value
        assert isinstance(settings.proj_version, Version)
        assert settings.proj_lang == "verilog"  # Default value
        assert settings.switch_matrix_debug_signal is False
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

        # user_config_dir should be created and exist
        assert settings.user_config_dir.exists()
        assert settings.user_config_dir.is_dir()
        assert settings.proj_dir == project
        assert settings.proj_lang == "vhdl"
        assert settings.switch_matrix_debug_signal is True
        assert settings.proj_version_created == Version("1.2.3")

    def test_initialization_with_tool_paths_found(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test FABulousSettings initialization when tools are found in PATH."""
        # Clear all FAB_ environment variables
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        mock_which = mocker.patch("fabulous.fabulous_settings.which")
        mock_which.side_effect = lambda tool: {
            "yosys": "/usr/bin/yosys",
            "nextpnr-generic": "/usr/bin/nextpnr-generic",
            "iverilog": "/usr/bin/iverilog",
            "vvp": "/usr/bin/vvp",
        }.get(tool)

        settings = init_context(project)

        assert settings.yosys_path == Path("/usr/bin/yosys")
        assert settings.nextpnr_path == Path("/usr/bin/nextpnr-generic")
        assert settings.iverilog_path == Path("/usr/bin/iverilog")
        assert settings.vvp_path == Path("/usr/bin/vvp")

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
        """Test init context in api mode"""
        mocker.patch("fabulous.fabulous_settings.which", return_value=None)
        settings = get_context()
        assert settings.yosys_path == "yosys"
        assert settings.nextpnr_path == "nextpnr-generic"

    def test_pdk_hash_from_env(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that pdk_hash is read from FAB_PDK_HASH environment variable."""
        monkeypatch.setenv("FAB_PDK_HASH", "abc123def456")
        mocker.patch("fabulous.fabulous_settings.which", return_value=None)
        mocker.patch("ciel.manage.enable")

        settings = init_context(project)
        assert settings.pdk_hash == "abc123def456"


class TestFieldValidators:
    """Test cases for field validators in FABulousSettings."""

    def test_parse_version_str_with_string(self) -> None:
        """Test parse_version validator with string input."""
        result = FABulousSettings.parse_version_str("3.4.5")
        assert isinstance(result, Version)
        assert result == Version("3.4.5")

    def test_parse_version_with_version_object(self) -> None:
        """Test parse_version validator with Version object input."""
        version_obj = Version("4.5.6")
        result = FABulousSettings.parse_version_str(version_obj)
        assert isinstance(result, Version)
        assert result == version_obj

    def test_validate_proj_lang_verilog(self) -> None:
        """Test validate_proj_lang validator with verilog."""
        result = FABulousSettings.validate_proj_lang("verilog")
        assert result == "verilog"

    def test_validate_proj_lang_vhdl(self) -> None:
        """Test validate_proj_lang validator with vhdl."""
        result = FABulousSettings.validate_proj_lang("vhdl")
        assert result == "vhdl"

    def test_validate_proj_lang_invalid(self) -> None:
        """Test validate_proj_lang validator with invalid language."""
        with pytest.raises(ValueError, match="Invalid project language"):
            FABulousSettings.validate_proj_lang("python")

    def test_ensure_user_config_dir_creates_directory(self, tmp_path: Path) -> None:
        """Test ensure_user_config_dir creates directory if it doesn't exist."""
        config_dir = tmp_path / "config" / "nested"
        assert not config_dir.exists()

        result = FABulousSettings.ensure_user_config_dir(config_dir)

        assert result == config_dir
        assert config_dir.exists()
        assert config_dir.is_dir()

    def test_ensure_user_config_dir_handles_existing_directory(
        self, tmp_path: Path
    ) -> None:
        """Test ensure_user_config_dir validator with existing directory."""
        config_dir = tmp_path / "existing_config"
        config_dir.mkdir()

        result = FABulousSettings.ensure_user_config_dir(config_dir)

        assert result == config_dir
        assert config_dir.exists()
        assert config_dir.is_dir()

    def test_ensure_user_config_dir_handles_none(self) -> None:
        """Test ensure_user_config_dir validator correctly handles None values."""
        result = FABulousSettings.ensure_user_config_dir(None)
        assert result is None

    def test_is_valid_project_dir_with_fabulous_directory(self, tmp_path: Path) -> None:
        """Test is_valid_project_dir validator with valid FABulous project."""
        project_dir = tmp_path / "valid_project"
        project_dir.mkdir()
        fabulous_dir = project_dir / ".FABulous"
        fabulous_dir.mkdir()

        result = FABulousSettings.is_valid_project_dir(project_dir)
        assert result == project_dir

    def test_is_valid_project_dir_without_fabulous_directory(
        self, tmp_path: Path
    ) -> None:
        """Test is_valid_project_dir validator with directory missing .FABulous."""
        project_dir = tmp_path / "invalid_project"
        project_dir.mkdir()

        with pytest.raises(ValueError, match="is not a FABulous project"):
            FABulousSettings.is_valid_project_dir(project_dir)

    def test_is_valid_project_dir_with_none(self) -> None:
        """Test is_valid_project_dir validator with None value."""
        with pytest.raises(ValueError, match="Project directory is not set"):
            FABulousSettings.is_valid_project_dir(None)


class TestToolPathResolution:
    """Test cases for tool path resolution validator."""

    def test_resolve_tool_paths_explicit_value(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths when value is explicitly provided."""
        explicit_path = Path("/custom/tool/path")
        mock_info = mocker.Mock()
        mock_info.field_name = "yosys_path"

        mock_which = mocker.patch("fabulous.fabulous_settings.which")
        result = FABulousSettings.resolve_tool_paths(explicit_path, mock_info)
        assert result == explicit_path
        mock_which.assert_not_called()

    def test_resolve_tool_paths_yosys_found(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths for yosys when tool is found."""
        mock_info = mocker.Mock()
        mock_info.field_name = "yosys_path"

        mock_which = mocker.patch(
            "fabulous.fabulous_settings.which", return_value="/usr/bin/yosys"
        )

        result = FABulousSettings.resolve_tool_paths(None, mock_info)

        assert result == Path("/usr/bin/yosys").resolve()
        mock_which.assert_called_once_with("yosys")

    def test_resolve_tool_paths_tool_not_found(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths when tool is not found in PATH."""
        mock_info = mocker.Mock()
        mock_info.field_name = "yosys_path"

        mock_which = mocker.patch("fabulous.fabulous_settings.which", return_value=None)

        result = FABulousSettings.resolve_tool_paths(None, mock_info)

        assert result == "yosys"
        mock_which.assert_called_once_with("yosys")


class TestContextMethods:
    """Test cases for the new context management methods."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        reset_context()

    def teardown_method(self) -> None:
        """Clean up context after each test."""
        reset_context()

    def test_init_context_basic(self, project: Path) -> None:
        """Test basic context initialization."""
        settings = init_context(project_dir=project)

        assert isinstance(settings, FABulousSettings)
        assert settings.proj_dir == project

    def test_init_context_with_project_dir(self, project: Path) -> None:
        """Test context initialization with project directory."""
        settings = init_context(project_dir=project)

        assert settings.proj_dir == project

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
        """Test context initialization with project .env file."""
        # Create project .env file
        project_env = tmp_path / "project.env"
        project_env.touch()
        set_key(project_env, "FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")
        set_key(project_env, "FAB_PROJ_LANG", "verilog")

        settings = init_context(project_dir=project, project_dot_env=project_env)

        assert settings.switch_matrix_debug_signal is True
        assert settings.proj_lang == "verilog"

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
        self, project: Path, tmp_path: Path
    ) -> None:
        """Test that missing global .env file produces warning but doesn't fail."""
        nonexistent_env = tmp_path / "nonexistent.env"

        # This should work without raising an exception
        settings = init_context(project_dir=project, global_dot_env=nonexistent_env)

        assert isinstance(settings, FABulousSettings)
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

    def test_context_singleton_behavior(self, project: Path) -> None:
        """Test that context follows singleton pattern."""
        init_context(project_dir=project)

        context1 = get_context()
        context2 = get_context()

        assert context1 is context2  # Same instance

    def test_init_context_with_env_var_overrides(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that environment variables override .env file settings."""
        # Create .env file
        env_file = tmp_path / "test.env"
        env_file.touch()
        set_key(env_file, "FAB_PROJ_LANG", "vhdl")
        set_key(env_file, "FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "false")

        # Set environment variable that should override .env
        monkeypatch.setenv("FAB_PROJ_LANG", "verilog")

        settings = init_context(project_dir=project, global_dot_env=env_file)

        # Environment variable should override .env file
        assert settings.proj_lang == "verilog"
        # .env file setting should still apply where no env var exists
        assert settings.switch_matrix_debug_signal is False

    def test_context_with_different_env_file_combinations(
        self, project: Path, tmp_path: Path
    ) -> None:
        """Test various combinations of .env files."""
        # Remove the project's default .env file to test precedence properly
        project_default_env = project / ".FABulous" / ".env"
        if project_default_env.exists():
            project_default_env.unlink()

        # Test with only global .env
        global_env = tmp_path / "global.env"
        global_env.touch()
        set_key(global_env, "FAB_PROJ_VERSION_CREATED", "2.0.0")

        settings1 = init_context(project_dir=project, global_dot_env=global_env)
        assert settings1.proj_version_created == Version("2.0.0")

        reset_context()

        # Test with only project .env
        project_env = tmp_path / "project.env"
        project_env.touch()
        set_key(project_env, "FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")

        settings2 = init_context(project_dir=project, project_dot_env=project_env)
        assert settings2.switch_matrix_debug_signal is True

        reset_context()

        # Test with both (project should override global)
        # Clear previous content and set new values
        global_env.write_text("")  # Clear file
        set_key(global_env, "FAB_PROJ_LANG", "vhdl")
        set_key(global_env, "FAB_PROJ_VERSION_CREATED", "1.0.0")

        project_env.write_text("")  # Clear file
        set_key(project_env, "FAB_PROJ_LANG", "verilog")
        set_key(project_env, "FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")

        settings3 = init_context(
            project_dir=project,
            global_dot_env=global_env,
            project_dot_env=project_env,
        )
        assert settings3.proj_lang == "verilog"  # Overridden by project
        assert settings3.proj_version_created == Version("1.0.0")  # From global
        assert settings3.switch_matrix_debug_signal is True  # From project

    def test_context_thread_safety_basics(self, project: Path) -> None:
        """Basic test for context state consistency."""
        # Initialize context
        settings = init_context(project_dir=project)

        # Multiple get_context calls should return the same instance
        context1 = get_context()
        context2 = get_context()
        context3 = get_context()

        assert context1 is settings
        assert context2 is settings
        assert context3 is settings
        assert context1 is context2 is context3

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

    def test_debug_env_variable(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that the DEBUG environment variable is respected."""
        monkeypatch.setenv("FAB_DEBUG", "1")

        settings = init_context(project_dir=project)

        assert settings.debug is True

        monkeypatch.setenv("FAB_DEBUG", "True")

        settings = init_context(project_dir=project)

        assert settings.debug is True


class TestIntegration:
    """Integration tests for FABulous settings functionality with new context system."""

    def test_complete_context_workflow(
        self,
        project: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
    ) -> None:
        """Test complete workflow from context initialization to settings usage."""
        reset_context()

        # Clear all FAB_ environment variables first
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Create .env files
        global_env = tmp_path / "global.env"
        global_env.touch()
        set_key(global_env, "FAB_PROJ_LANG", "vhdl")
        set_key(global_env, "FAB_YOSYS_PATH", "/custom/yosys")

        # Modify the project's existing .env file instead of creating a new one
        project_env = project / ".FABulous" / ".env"
        # Clear existing content and set new values
        project_env.write_text("")
        set_key(
            project_env, "FAB_PROJ_LANG", "vhdl"
        )  # Override to match global for consistency
        set_key(project_env, "FAB_PROJ_VERSION_CREATED", "2.0.0")

        # Set environment variables
        monkeypatch.setenv("FAB_PROJ_DIR", str(project))

        mocker.patch("fabulous.fabulous_settings.which", return_value=None)
        mocker.patch("pathlib.Path.exists", return_value=True)
        # Initialize context
        settings = init_context(project_dir=project, global_dot_env=global_env)

        # Verify context was initialized correctly
        context = get_context()
        assert context is settings

        assert settings.proj_dir == project
        assert settings.proj_lang == "vhdl"
        assert settings.proj_version_created == Version("2.0.0")
        assert settings.yosys_path == Path("/custom/yosys")

        # Test context reset
        reset_context()
        from fabulous.fabulous_settings import _context_instance

        assert _context_instance is None


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
            "fabulous.fabulous_settings.get_pdk_hash",
            return_value=recommended_hash,
        )
        monkeypatch.setenv("FAB_PDK_HASH", configured_hash)

        settings = init_context(project)
        assert settings.pdk_hash == configured_hash
        has_mismatch_warning = any(
            "PDK hash mismatch" in r.message for r in caplog.records
        )
        assert has_mismatch_warning is expect_mismatch_warning

    def test_system_exit_from_get_pdk_hash(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test graceful handling when get_pdk_hash raises SystemExit."""
        self._setup_pdk_env(project, monkeypatch, mocker)
        mocker.patch(
            "fabulous.fabulous_settings.get_pdk_hash",
            side_effect=SystemExit(1),
        )

        with pytest.raises(SystemExit):
            init_context(project)

    @pytest.mark.parametrize(
        ("pdk_name", "is_known_family"),
        [
            ("sky130", True),
            ("gf180mcu", True),
            ("ihp-sg13g2", True),
            ("custom_unknown_pdk", False),
        ],
    )
    def test_pdk_resolution_by_family(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        pdk_name: str,
        is_known_family: bool,
    ) -> None:
        """Test hash resolution for known families and skipping for unknown ones."""
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
            "fabulous.fabulous_settings.get_pdk_hash",
            return_value=expected_hash,
        )
        mock_enable = mocker.patch("ciel.manage.enable")

        settings = init_context(project)

        if is_known_family:
            assert settings.pdk_hash == expected_hash
            mock_enable.assert_called_once()
            call_kwargs = mock_enable.call_args[1]
            assert call_kwargs["pdk"] == pdk_name
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
            "fabulous.fabulous_settings.get_pdk_hash",
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
            "fabulous.fabulous_settings.get_pdk_hash",
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
        (ciel_home / "ihp-sg13g2").mkdir()
        mocker.patch(
            "fabulous.fabulous_settings.get_ciel_home",
            return_value=str(ciel_home),
        )
        mocker.patch(
            "fabulous.fabulous_settings.get_pdk_hash",
            return_value="auto_hash",
        )

        settings = init_context(project)
        assert settings.pdk_root == ciel_home / "ihp-sg13g2"
        assert settings.pdk_hash == "auto_hash"

    @pytest.mark.parametrize(
        ("set_pdk_env", "set_pdk_root_env", "pdk_name", "expected_match"),
        [
            pytest.param(
                True,
                False,
                "custom_unknown_pdk",
                "FAB_PDK_ROOT",
                id="pdk_without_root",
            ),
            pytest.param(
                False,
                True,
                "ihp-sg13g2",
                "FAB_PDK",
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
