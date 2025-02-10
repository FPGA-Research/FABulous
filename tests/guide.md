# Testing Guide for FABulous

This guide explains how to write tests for the FABulous project using pytest.

## Testing Infrastructure

We use `pytest` as our testing framework. Our testing infrastructure is set up in `tests/CLI_test/conftest.py`, which provides several useful fixtures and utilities.

### Key Testing Components

#### tmp_path Fixture

`tmp_path` is a built-in pytest fixture that provides a temporary directory unique to each test function. It's particularly useful for our CLI tests as we works with files creation.

Example usage:

```python
def test_example(tmp_path):
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
