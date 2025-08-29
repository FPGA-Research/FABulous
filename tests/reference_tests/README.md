# FABulous Reference Testing

A pytest-based framework for testing FABulous against reference projects with regression testing capabilities.

It automatically downloads reference projects from a GitHub repository,
runs specified FABulous commands, and compares the outputs against expected results using git-style diffs.

The default reference projects are hosted in the
[FABulous-demo-projects repo](https://github.com/FPGA-Research/FABulous-demo-projects)

## Quick Start

```bash
# Run all reference tests
pytest tests/reference_tests/

```

## Features

- **Flexible Configuration**: YAML-based project configuration with skip support
- **Run or Diff Mode**: Either just run FABulous commands or run + compare outputs
  - **Run** mode checks for command execution errors only and if `expected_outputs` are defined
  - **Diff** Mode copies the project to a temp directory, runs commands, and compares outputs against the original project
- **File Pattern Matching**: Configure which files to include/exclude in comparisons
- **Git-style Diffs**: Shows detailed unified diff output when tests fail
- **GitHub Integration**: Automatically download reference projects from repository

## YAML-Configuration

Our default configuration file can be found here:
[FABulous-demo-projects/refernce_projects_config.yaml](https://github.com/FPGA-Research/FABulous-demo-projects/blob/main/reference_projects_config.yaml)

### Configuration Options

```yaml
reference_projects: Header for all reference projects
  - name:  Unique identifier for the project.
    path: Path to the project within the repository.
    language: Project language - "verilog" or "vhdl"
    test_mode: Test mode "diff"  or "run"
    description: A brief description of the project.
    expected_outputs: (Optional) Check of the following list of files exists after run
    include_patterns: (Optional) Only for "diff" mode.
      A list of glob patterns, which files to diff:
      Default include_patterns: ["*.v", "*.sv", "*.vhd", "*.vhdl", "*.csv", "*.list", "*txt", "*.bin"]
    exclude_patterns: (Optional) Only for "diff" mode.
      A list of glob patterns, which files to exclude from diff
      Default exclude_patterns: [] # None excluded
    commands: (optional) List of FABulous commands to run.
      Default commands: ["load_fabric", "run_FABulous_fabric"]
    skip_reason: (Optional) Reason to skip this project.
      If provided, the test will be skipped with this reason.
```

### Example Configuration

This is an example configuration for a Verilog project:

```yaml
reference_projects:
  - name: "my_verilog_project"
    path: "./tests/reference_tests/projects/my_verilog_project"
    language: "verilog"
    test_mode: "diff" # or "run"
    description: "My custom FABulous project"
    include_patterns: ["*.v", "*.json", "*.csv", "*.txt"] # optional
    exclude_patterns: ["*_test.v", "*.log"] # optional
    expected_outputs: # optional
      - "Fabric/eFPGA_top.v"
      - "Fabric/eFPGA.v"
      - "Tile/LUT4AB/LUT4AB.v"
    commands: #optional
      - "load_fabric"
      - "run_FABulous_fabric"
      - "gen_user_design_wrapper user_design/sequential_16bit_en.v user_design/top_wrapper.v"
      - "run_FABulous_bitstream ./user_design/sequential_16bit_en.v"
      - "run_simulation fst ./user_design/sequential_16bit_en.bin"
```

## Command Line Options

- `--repo-url`: Specify custom GitHub repository URL
- `--projects-dir`: Specify local projects directory
- `--reference-projects-config`: Path to YAML config file

## Examples

```bash
# Test specific project patterns (matches "verilog" in the project names)
pytest tests/reference_tests/ -k "verilog"

# Run with custom repository
pytest tests/reference_tests/ --repo-url "https://github.com/myuser/my-projects.git"

# Run with custom YAML config
pytest tests/reference_tests/ ---reference-projects-config "./test/my_custom_config.yaml"

# Generate pytest report
pytest tests/reference_tests/ --html=report.html
```
