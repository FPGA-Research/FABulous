import argparse
import os
from pathlib import Path

import pytest
from packaging.version import Version
from pytest_mock import MockerFixture

from FABulous.custom_exception import EnvironmentNotSet
from FABulous.FABulous_settings import (
    FABulousSettings,
    setup_global_env_vars,
    setup_project_env_vars,
)


class TestFABulousSettings:
    """Test cases for FABulousSettings class."""

    def test_default_initialization(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test FABulousSettings initialization with default values and no environment variables."""
        # Clear all FAB_ environment variables
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        # Set a valid root directory
        test_root = tmp_path / "fab_root"
        test_root.mkdir()
        monkeypatch.setenv("FAB_ROOT", str(test_root))

        # Mock which to return None (no tools found)
        mocker.patch("FABulous.FABulous_settings.which", return_value=None)

        settings = FABulousSettings()

        assert settings.root == test_root
        assert settings.yosys_path is None
        assert settings.nextpnr_path is None
        assert settings.iverilog_path is None
        assert settings.vvp_path is None
        assert settings.proj_dir == Path.cwd()
        assert settings.fabulator_root is None
        assert settings.oss_cad_suite is None
        assert isinstance(settings.proj_version_created, Version)
        assert settings.proj_version_created == Version("0.0.1")
        assert isinstance(settings.proj_version, Version)
        assert settings.proj_lang == "verilog"
        assert settings.switch_matrix_debug_signal is False

    def test_initialization_with_environment_variables(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test FABulousSettings initialization with environment variables."""
        test_root = tmp_path / "test_root"
        test_root.mkdir()
        test_proj_dir = tmp_path / "test_proj"
        test_proj_dir.mkdir()

        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        monkeypatch.setenv("FAB_ROOT", str(test_root))
        monkeypatch.setenv("FAB_PROJ_DIR", str(test_proj_dir))
        monkeypatch.setenv("FAB_PROJ_LANG", "vhdl")
        monkeypatch.setenv("FAB_SWITCH_MATRIX_DEBUG_SIGNAL", "true")
        monkeypatch.setenv("FAB_PROJ_VERSION_CREATED", "1.2.3")

        # Mock which to return None (no tools found)
        mocker.patch("FABulous.FABulous_settings.which", return_value=None)

        settings = FABulousSettings()

        assert settings.root == test_root
        assert settings.proj_dir == test_proj_dir
        assert settings.proj_lang == "vhdl"
        assert settings.switch_matrix_debug_signal is True
        assert settings.proj_version_created == Version("1.2.3")

    def test_initialization_with_tool_paths_found(self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
        """Test FABulousSettings initialization when tools are found in PATH."""
        # Clear all FAB_ environment variables
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        mock_which = mocker.patch("FABulous.FABulous_settings.which")
        mock_which.side_effect = lambda tool: {
            "yosys": "/usr/bin/yosys",
            "nextpnr-generic": "/usr/bin/nextpnr-generic",
            "iverilog": "/usr/bin/iverilog",
            "vvp": "/usr/bin/vvp",
        }.get(tool)

        settings = FABulousSettings()

        assert settings.yosys_path == Path("/usr/bin/yosys")
        assert settings.nextpnr_path == Path("/usr/bin/nextpnr-generic")
        assert settings.iverilog_path == Path("/usr/bin/iverilog")
        assert settings.vvp_path == Path("/usr/bin/vvp")

    def test_initialization_with_explicit_tool_paths(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test FABulousSettings initialization with explicitly set tool paths."""
        # Clear all FAB_ environment variables first
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        yosys_path = "/custom/yosys"
        nextpnr_path = "/custom/nextpnr-generic"

        monkeypatch.setenv("FAB_YOSYS_PATH", yosys_path)
        monkeypatch.setenv("FAB_NEXTPNR_PATH", nextpnr_path)

        mocker.patch("FABulous.FABulous_settings.which", return_value=None)

        settings = FABulousSettings()

        assert settings.yosys_path == Path(yosys_path)
        assert settings.nextpnr_path == Path(nextpnr_path)
        # Tools not explicitly set should still be resolved via which
        assert settings.iverilog_path is None
        assert settings.vvp_path is None


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

    def test_is_dir_valid_directory(self, tmp_path: Path) -> None:
        """Test is_dir validator with valid directory."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        result = FABulousSettings.is_dir(test_dir)
        assert result == test_dir

    def test_is_dir_invalid_directory(self, tmp_path: Path) -> None:
        """Test is_dir validator with invalid directory."""
        non_existent_dir = tmp_path / "non_existent"

        with pytest.raises(ValueError, match="is not a valid directory"):
            FABulousSettings.is_dir(non_existent_dir)

    def test_is_dir_file_instead_of_directory(self, tmp_path: Path) -> None:
        """Test is_dir validator with file instead of directory."""
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test content")

        with pytest.raises(ValueError, match="is not a valid directory"):
            FABulousSettings.is_dir(test_file)

    def test_is_dir_handles_none(self) -> None:
        """Test is_dir validator correctly handles None values (bug now fixed)."""
        result = FABulousSettings.is_dir(None)
        assert result is None

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
        with pytest.raises(ValueError, match="Project language must be either 'verilog' or 'vhdl'"):
            FABulousSettings.validate_proj_lang("python")

    def test_validate_proj_lang_case_sensitive(self) -> None:
        """Test validate_proj_lang validator is case sensitive."""
        with pytest.raises(ValueError, match="Project language must be either 'verilog' or 'vhdl'"):
            FABulousSettings.validate_proj_lang("VERILOG")


class TestToolPathResolution:
    """Test cases for tool path resolution validator."""

    def test_resolve_tool_paths_explicit_value(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths when value is explicitly provided."""
        explicit_path = Path("/custom/tool/path")
        mock_info = mocker.Mock()
        mock_info.field_name = "yosys_path"

        mock_which = mocker.patch("FABulous.FABulous_settings.which")
        result = FABulousSettings.resolve_tool_paths(explicit_path, mock_info)
        assert result == explicit_path
        mock_which.assert_not_called()

    def test_resolve_tool_paths_yosys_found(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths for yosys when tool is found."""
        mock_info = mocker.Mock()
        mock_info.field_name = "yosys_path"

        mock_which = mocker.patch("FABulous.FABulous_settings.which", return_value="/usr/bin/yosys")

        result = FABulousSettings.resolve_tool_paths(None, mock_info)

        assert result == Path("/usr/bin/yosys").resolve()
        mock_which.assert_called_once_with("yosys")

    def test_resolve_tool_paths_nextpnr_found(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths for nextpnr when tool is found."""
        mock_info = mocker.Mock()
        mock_info.field_name = "nextpnr_path"

        mock_which = mocker.patch("FABulous.FABulous_settings.which", return_value="/usr/bin/nextpnr-generic")

        result = FABulousSettings.resolve_tool_paths(None, mock_info)

        assert result == Path("/usr/bin/nextpnr-generic").resolve()
        mock_which.assert_called_once_with("nextpnr-generic")

    def test_resolve_tool_paths_iverilog_found(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths for iverilog when tool is found."""
        mock_info = mocker.Mock()
        mock_info.field_name = "iverilog_path"

        mock_which = mocker.patch("FABulous.FABulous_settings.which", return_value="/usr/bin/iverilog")

        result = FABulousSettings.resolve_tool_paths(None, mock_info)

        assert result == Path("/usr/bin/iverilog").resolve()
        mock_which.assert_called_once_with("iverilog")

    def test_resolve_tool_paths_vvp_found(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths for vvp when tool is found."""
        mock_info = mocker.Mock()
        mock_info.field_name = "vvp_path"

        mock_which = mocker.patch("FABulous.FABulous_settings.which", return_value="/usr/bin/vvp")

        result = FABulousSettings.resolve_tool_paths(None, mock_info)

        assert result == Path("/usr/bin/vvp").resolve()
        mock_which.assert_called_once_with("vvp")

    def test_resolve_tool_paths_tool_not_found(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths when tool is not found in PATH."""
        mock_info = mocker.Mock()
        mock_info.field_name = "yosys_path"

        mock_which = mocker.patch("FABulous.FABulous_settings.which", return_value=None)

        result = FABulousSettings.resolve_tool_paths(None, mock_info)

        assert result is None
        mock_which.assert_called_once_with("yosys")

    def test_resolve_tool_paths_unknown_field(self, mocker: MockerFixture) -> None:
        """Test resolve_tool_paths with unknown field name."""
        mock_info = mocker.Mock()
        mock_info.field_name = "unknown_path"

        mock_which = mocker.patch("FABulous.FABulous_settings.which")
        result = FABulousSettings.resolve_tool_paths(None, mock_info)

        assert result is None
        mock_which.assert_not_called()


class TestSetupGlobalEnvVars:
    """Test cases for setup_global_env_vars function."""

    def test_fab_root_not_set_with_fabric_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test setup_global_env_vars when FAB_ROOT is not set and fabric_files exists."""
        # Create a mock FABulous module structure
        fab_module_dir = tmp_path / "FABulous"
        fab_module_dir.mkdir()
        fabric_files_dir = fab_module_dir / "fabric_files"
        fabric_files_dir.mkdir()

        # Mock __file__ to point to our test directory
        mock_file = str(fab_module_dir / "FABulous_settings.py")

        # Clear FAB_ROOT environment variable
        monkeypatch.delenv("FAB_ROOT", raising=False)

        args = argparse.Namespace(globalDotEnv=None, project_dir=".")

        mocker.patch("FABulous.FABulous_settings.__file__", mock_file)
        setup_global_env_vars(args)

        assert os.environ["FAB_ROOT"] == str(fab_module_dir)

    def test_fab_root_not_set_fallback_to_parent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test setup_global_env_vars fallback to parent directory when fabric_files doesn't exist."""
        # Create directory structure without fabric_files
        fab_module_dir = tmp_path / "FABulous"
        fab_module_dir.mkdir()

        mock_file = str(fab_module_dir / "FABulous_settings.py")

        monkeypatch.delenv("FAB_ROOT", raising=False)

        args = argparse.Namespace(globalDotEnv=None, project_dir=".")

        mocker.patch("FABulous.FABulous_settings.__file__", mock_file)
        setup_global_env_vars(args)

        assert os.environ["FAB_ROOT"] == str(tmp_path)

    def test_fab_root_set_existing_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test setup_global_env_vars when FAB_ROOT is already set to existing directory."""
        test_root = tmp_path / "existing_root"
        test_root.mkdir()

        monkeypatch.setenv("FAB_ROOT", str(test_root))

        args = argparse.Namespace(globalDotEnv=None, project_dir=".")

        setup_global_env_vars(args)

        assert os.environ["FAB_ROOT"] == str(test_root)

    def test_fab_root_set_with_fabulous_subdirectory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test setup_global_env_vars when FAB_ROOT has FABulous subdirectory."""
        test_root = tmp_path / "root"
        test_root.mkdir()
        fabulous_dir = test_root / "FABulous"
        fabulous_dir.mkdir()

        monkeypatch.setenv("FAB_ROOT", str(test_root))

        args = argparse.Namespace(globalDotEnv=None, project_dir=".")

        setup_global_env_vars(args)

        assert os.environ["FAB_ROOT"] == str(fabulous_dir)

    def test_fab_root_set_non_existent_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test setup_global_env_vars exits when FAB_ROOT is set to non-existent directory."""
        non_existent = "/non/existent/path"
        monkeypatch.setenv("FAB_ROOT", non_existent)

        args = argparse.Namespace(globalDotEnv=None, project_dir=".")

        with pytest.raises(SystemExit):
            setup_global_env_vars(args)

    def test_global_dot_env_file_loading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test loading global .env file when specified."""
        # Create test .env file
        env_file = tmp_path / "global.env"
        env_file.write_text("TEST_VAR=test_value\n")

        # Set up basic environment
        fab_root = tmp_path / "fab_root"
        fab_root.mkdir()
        monkeypatch.setenv("FAB_ROOT", str(fab_root))

        args = argparse.Namespace(globalDotEnv=str(env_file), project_dir=".")

        mock_load_dotenv = mocker.patch("FABulous.FABulous_settings.load_dotenv")
        setup_global_env_vars(args)
        mock_load_dotenv.assert_called_once_with(env_file)

    def test_global_dot_env_directory_with_env_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test loading .env file from specified directory."""
        # Create directory with .env file
        env_dir = tmp_path / "env_dir"
        env_dir.mkdir()
        env_file = env_dir / ".env"
        env_file.write_text("TEST_VAR=test_value\n")

        fab_root = tmp_path / "fab_root"
        fab_root.mkdir()
        monkeypatch.setenv("FAB_ROOT", str(fab_root))

        args = argparse.Namespace(globalDotEnv=str(env_dir), project_dir=".")

        mock_load_dotenv = mocker.patch("FABulous.FABulous_settings.load_dotenv")
        setup_global_env_vars(args)
        mock_load_dotenv.assert_called_once_with(env_file)

    def test_proj_dir_env_var_setting(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test setting FAB_PROJ_DIR environment variable."""
        fab_root = tmp_path / "fab_root"
        fab_root.mkdir()
        monkeypatch.setenv("FAB_ROOT", str(fab_root))
        monkeypatch.delenv("FAB_PROJ_DIR", raising=False)

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        args = argparse.Namespace(globalDotEnv=None, project_dir=str(project_dir))

        setup_global_env_vars(args)

        assert os.environ["FAB_PROJ_DIR"] == str(project_dir.absolute())

    def test_oss_cad_suite_path_export(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test exporting oss-cad-suite bin path to PATH."""
        fab_root = tmp_path / "fab_root"
        fab_root.mkdir()
        oss_cad_path = tmp_path / "oss-cad-suite"
        oss_cad_path.mkdir()

        monkeypatch.setenv("FAB_ROOT", str(fab_root))
        monkeypatch.setenv("FAB_OSS_CAD_SUITE", str(oss_cad_path))

        original_path = os.environ.get("PATH", "")

        args = argparse.Namespace(globalDotEnv=None, project_dir=".")

        setup_global_env_vars(args)

        expected_path = original_path + os.pathsep + str(oss_cad_path) + "/bin"
        assert os.environ["PATH"] == expected_path


class TestSetupProjectEnvVars:
    """Test cases for setup_project_env_vars function."""

    def test_fab_proj_dir_not_set_raises_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test setup_project_env_vars raises exception when FAB_PROJ_DIR not set."""
        monkeypatch.delenv("FAB_PROJ_DIR", raising=False)

        args = argparse.Namespace(projectDotEnv=None, writer=None)

        with pytest.raises(EnvironmentNotSet, match="FAB_PROJ_DIR environment variable not set"):
            setup_project_env_vars(args)

    def test_project_dot_env_file_loading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test loading project .env file when specified."""
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        env_file = proj_dir / "project.env"
        env_file.write_text("PROJECT_VAR=project_value\n")

        monkeypatch.setenv("FAB_PROJ_DIR", str(proj_dir))

        args = argparse.Namespace(projectDotEnv=str(env_file), writer=None)

        mock_load_dotenv = mocker.patch("FABulous.FABulous_settings.load_dotenv")
        setup_project_env_vars(args)
        mock_load_dotenv.assert_called_once_with(env_file)

    def test_fabulous_dot_env_loading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test loading .env from .FABulous directory."""
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        fabulous_dir = proj_dir / ".FABulous"
        fabulous_dir.mkdir()
        env_file = fabulous_dir / ".env"
        env_file.write_text("FABULOUS_VAR=fabulous_value\n")

        monkeypatch.setenv("FAB_PROJ_DIR", str(proj_dir))

        args = argparse.Namespace(projectDotEnv=None, writer=None)

        mock_load_dotenv = mocker.patch("FABulous.FABulous_settings.load_dotenv")
        setup_project_env_vars(args)
        mock_load_dotenv.assert_called_once_with(env_file)

    def test_parent_dot_env_loading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test loading .env from parent directory when .FABulous/.env doesn't exist."""
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        fabulous_dir = proj_dir / ".FABulous"
        fabulous_dir.mkdir()
        env_file = proj_dir / ".env"
        env_file.write_text("PARENT_VAR=parent_value\n")

        monkeypatch.setenv("FAB_PROJ_DIR", str(proj_dir))

        args = argparse.Namespace(projectDotEnv=None, writer=None)

        mock_load_dotenv = mocker.patch("FABulous.FABulous_settings.load_dotenv")
        setup_project_env_vars(args)
        mock_load_dotenv.assert_called_once_with(env_file)

    def test_writer_override_project_lang(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test writer argument overrides FAB_PROJ_LANG environment variable."""
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()

        monkeypatch.setenv("FAB_PROJ_DIR", str(proj_dir))
        monkeypatch.setenv("FAB_PROJ_LANG", "verilog")

        args = argparse.Namespace(projectDotEnv=None, writer="vhdl")

        setup_project_env_vars(args)

        assert os.environ["FAB_PROJ_LANG"] == "vhdl"

    def test_writer_no_override_when_same(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test writer argument doesn't override when same as current value."""
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()

        monkeypatch.setenv("FAB_PROJ_DIR", str(proj_dir))
        monkeypatch.setenv("FAB_PROJ_LANG", "vhdl")

        args = argparse.Namespace(projectDotEnv=None, writer="vhdl")

        # Should not generate warning when values are the same
        setup_project_env_vars(args)

        assert os.environ["FAB_PROJ_LANG"] == "vhdl"


class TestIntegration:
    """Integration tests for FABulous settings functionality."""

    def test_complete_environment_setup_workflow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test complete workflow from environment setup to settings creation."""
        # Clear all FAB_ environment variables first
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Set up directory structure
        fab_root = tmp_path / "FABulous"
        fab_root.mkdir()
        fabric_files_dir = fab_root / "fabric_files"
        fabric_files_dir.mkdir()

        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        fabulous_dir = proj_dir / ".FABulous"
        fabulous_dir.mkdir()

        # Create .env files
        global_env = fab_root / ".env"
        global_env.write_text("FAB_PROJ_LANG=vhdl\nFAB_YOSYS_PATH=/custom/yosys\n")

        project_env = fabulous_dir / ".env"
        project_env.write_text("FAB_PROJ_VERSION_CREATED=2.0.0\n")

        # Mock __file__ location
        mock_file = str(fab_root / "FABulous_settings.py")

        args = argparse.Namespace(globalDotEnv=None, project_dir=str(proj_dir), projectDotEnv=None, writer=None)

        mocker.patch("FABulous.FABulous_settings.__file__", mock_file)
        mocker.patch("FABulous.FABulous_settings.which", return_value=None)

        # Set up global environment
        setup_global_env_vars(args)

        # Set up project environment
        setup_project_env_vars(args)

        # Create settings instance
        settings = FABulousSettings()

        assert settings.root == fab_root
        assert settings.proj_dir == proj_dir
        assert settings.proj_lang == "vhdl"
        assert settings.proj_version_created == Version("2.0.0")
        assert settings.yosys_path == Path("/custom/yosys")

    def test_tool_resolution_with_environment_setup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test tool path resolution after oss-cad-suite PATH setup."""
        # Clear all FAB_ environment variables first
        for key in list(os.environ.keys()):
            if key.startswith("FAB_"):
                monkeypatch.delenv(key, raising=False)

        # Set minimal PATH to avoid system tools
        monkeypatch.setenv("PATH", "/bin:/usr/bin")

        fab_root = tmp_path / "fab_root"
        fab_root.mkdir()
        oss_cad_path = tmp_path / "oss-cad-suite"
        oss_cad_bin = oss_cad_path / "bin"
        oss_cad_bin.mkdir(parents=True)

        # Create mock tools
        yosys_tool = oss_cad_bin / "yosys"
        yosys_tool.write_text("#!/bin/bash\necho yosys")
        yosys_tool.chmod(0o755)

        monkeypatch.setenv("FAB_ROOT", str(fab_root))
        monkeypatch.setenv("FAB_OSS_CAD_SUITE", str(oss_cad_path))

        args = argparse.Namespace(globalDotEnv=None, project_dir=".")

        # Set up environment (this should add oss-cad-suite/bin to PATH)
        setup_global_env_vars(args)

        # Now create settings - tools should be found in PATH
        mock_which = mocker.patch("FABulous.FABulous_settings.which")
        mock_which.side_effect = lambda tool: str(oss_cad_bin / tool) if tool == "yosys" else None

        settings = FABulousSettings()

        assert settings.yosys_path == Path(str(oss_cad_bin / "yosys")).resolve()
