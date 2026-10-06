# Testing Guide for FABulous

This guide explains how to write tests for the FABulous project using [pytest](https://docs.pytest.org/en/stable/).

## Running Tests

Install the development environment with `uv sync`, then run the suite through the task runner at the top level directory:

```sh
task test
```

Arguments after `--` are forwarded to pytest, for example a single file or test case:

```sh
task test -- tests/repl_test/test_cli.py
task test -- -k <name_of_test_case>
```

Tests marked `slow` or `gl` are skipped unless `--runslow` or `--gl` is given.
For more details on what option can be used please check the pytest documentation.

## Testing Infrastructure

The shared fixtures live in `tests/conftest.py`; the REPL tests add their own in `tests/repl_test/conftest.py`.

### Key Testing Components

#### tmp_path Fixture

`tmp_path` is a built-in pytest fixture that provides a temporary directory unique to each test function.
The autouse `fabulous_test_environment` fixture also changes into it and points the user config directory and the ciel PDK home at it.

#### CLI Fixture and run_cmd

The `cli` fixture provides a pre-configured instance of `FABulousREPL` for testing. It:

- Creates a new project in a temporary directory
- Sets up the FABulous environment
- Loads the fabric configuration
- Returns a ready-to-use CLI instance

`run_cmd(cli, command)` runs one REPL command and returns nothing.
A failing command does not raise: check `cli.exit_code`.

Example usage:

```python
def test_cli_command(cli, caplog):
    run_cmd(cli, "your_command_here")
    log = normalize(caplog.text)

    # check is "something" in first line of log
    assert "something" in log[0]

    # or can do
    assert "something" in caplog.text
```

### Reference Tests

A pytest-based framework for testing FABulous against reference projects with regression testing capabilities.

It automatically downloads reference projects from a GitHub repository,
runs specified FABulous commands, and compares the outputs against expected results using git-style diffs.

The default reference projects are hosted in the
[FABulous-demo-projects repo](https://github.com/FPGA-Research/FABulous-demo-projects)

For more information, please check the [reference_test README](./reference_test/README.md)
