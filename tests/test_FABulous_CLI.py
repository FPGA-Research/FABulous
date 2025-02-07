import pytest

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI


@pytest.fixture
def cli_instance(tmp_path):
    # Instantiate CLI; use tmp_path for project and entering directory.
    cli = FABulous_CLI(writerType="verilog", projectDir=tmp_path, enteringDir=tmp_path)
    cli.verbose = True  # make CLI run in verbose mode for testing if needed
    return cli


def test_help(cli_instance, capsys):
    # Execute help command and capture output
    cli_instance.onecmd("help")
    out = capsys.readouterr().out
    # Assert that help text is printed (simple sanity check)
    assert "Available commands" in out or "help" in out


def test_exit(cli_instance):
    # Exit command should return True
    ret = cli_instance.do_exit("")
    assert ret is True


def test_exit_with_args(cli_instance):
    # Exit command should return True even with arguments
    ret = cli_instance.do_exit("some args")
    assert ret is True


def test_quit(cli_instance):
    # Quit command should be alias for exit
    ret = cli_instance.do_quit("")
    assert ret is True


def test_load_fabric_no_file(cli_instance, capsys):
    # Should fail when no fabric file exists
    cli_instance.do_load_fabric("")
    captured = capsys.readouterr()
    assert "No argument is given" in captured.err


def test_load_fabric_invalid_file(cli_instance, tmp_path, capsys):
    # Should fail with non-CSV file
    invalid_file = tmp_path / "test.txt"
    invalid_file.touch()
    cli_instance.do_load_fabric(str(invalid_file))
    captured = capsys.readouterr()
    assert "Only .csv files are supported" in captured.err


def test_print_bel_no_fabric(cli_instance, capsys):
    # Should fail when fabric not loaded
    cli_instance.do_print_bel("testbel")
    captured = capsys.readouterr()
    assert "Need to load fabric first" in captured.err


def test_print_tile_no_fabric(cli_instance, capsys):
    # Should fail when fabric not loaded
    cli_instance.do_print_tile("testtile")
    captured = capsys.readouterr()
    assert "Need to load fabric first" in captured.err


def test_gen_config_mem_no_fabric(cli_instance, capsys):
    # Commands requiring loaded fabric should be disabled initially
    cli_instance.do_gen_config_mem("testtile")
    captured = capsys.readouterr()
    assert "Fabric Flow commands are disabled" in str(captured.err)


def test_verbose_setting(cli_instance):
    # Should be able to toggle verbose setting
    assert cli_instance.verbose is True  # Set in fixture
    cli_instance.verbose = False
    assert cli_instance.verbose is False


def test_project_dir_setting(cli_instance, tmp_path):
    # Should be able to change project directory
    new_dir = tmp_path / "new_project"
    new_dir.mkdir()
    cli_instance.projectDir = new_dir
    assert cli_instance.projectDir == new_dir


def test_disabled_categories_initial(cli_instance):
    # Certain command categories should be disabled until fabric is loaded
    disabled = cli_instance.disabled_categories
    assert "Fabric Flow" in disabled
    assert "GUI" in disabled
    assert "Helper" in disabled


@pytest.fixture
def mock_fabric_csv(tmp_path):
    # Create a minimal mock fabric CSV file
    fabric_file = tmp_path / "fabric.csv"
    fabric_file.write_text("""
FABRIC,test_fabric,2,2
TILE,T1,1,1
TILE,T2,1,1
""")
    return fabric_file


def test_csvfile_setting(cli_instance, mock_fabric_csv):
    # Should be able to change CSV file path
    cli_instance.csvFile = mock_fabric_csv
    assert cli_instance.csvFile == mock_fabric_csv


def test_simulation_format_validation(cli_instance, capsys):
    # Should validate simulation format argument
    cli_instance.do_run_simulation("invalid test.bin")
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err.lower()


def test_simulation_file_validation(cli_instance, capsys):
    # Should validate simulation input file
    cli_instance.do_run_simulation("fst nonexistent.bin")
    captured = capsys.readouterr()
    assert "Cannot find" in captured.err


def test_entering_dir_preserved(cli_instance, tmp_path):
    # Should preserve and return to entering directory on exit
    original_dir = cli_instance.enteringDir
    cli_instance.do_exit("")
    assert original_dir == cli_instance.enteringDir


def test_extension_by_writer(tmp_path):
    # Should set correct file extension based on writer type
    verilog_cli = FABulous_CLI("verilog", tmp_path, tmp_path)
    assert verilog_cli.extension == "v"

    vhdl_cli = FABulous_CLI("vhdl", tmp_path, tmp_path)
    assert vhdl_cli.extension == "vhdl"
