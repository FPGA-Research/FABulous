# Testing Guide for FABulous

This guide explains how to write tests for the FABulous project using [pytest](https://docs.pytest.org/en/stable/).

## Prerequisites

Here we assume all the dependency required by FABulous is already installed.

You can install pytest using pip:

```sh
pip install pytest
```

## Running Tests

To run all the test, use the following command at the top level directory:

```sh
pytest
```

To run a test file, use the following command at the top level directory:

```sh
pytest <path_to_test_file>
```

To run a specific test case use the following command at the top level directory:

```sh
pytest -k <name_of_test_case>
```

For more details on what option can be used please check the pytest documentation.

## Testing Infrastructure

We use `pytest` as our testing framework. Our testing infrastructure is set up in `tests/CLI_test/conftest.py`, which provides several useful fixtures and utilities.

### Key Testing Components

#### tmp_path Fixture

`tmp_path` is a built-in pytest fixture that provides a temporary directory unique to each test function. It's particularly useful for us as we work with file creation.

Example usage:

```python
def test_example(tmp_path: Path):
    project_dir = tmp_path / "my_test_project"
    # Your test code here
```

#### CLI Fixture and run_cmd

The `cli` fixture provides a pre-configured instance of `FABulous_CLI` for testing. It:

- Creates a new project in a temporary directory
- Sets up the FABulous environment
- Loads the fabric configuration
- Returns a ready-to-use CLI instance

The `run_cmd` function is a utility for executing CLI commands and capturing their output. It:

- Takes a CLI instance and a command string
- Captures both stdout and stderr
- Returns normalized output as lists of lines
- Handles all the complexity of redirecting streams

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

For more information, please check the [reference_tests README](./reference_tests/README.md)

