# FABulous Reference Testing

A pytest-based framework for testing FABulous against reference projects with regression testing capabilities.

It automatically downloads reference projects from a GitHub repository,
runs specified FABulous commands, and compares the outputs against expected results using git-style diffs.

The default reference projects are hosted in the
[FABulous-demo-projects repo](https://github.com/FPGA-Research/FABulous-demo-projects)

## Quick Start

```bash
# Run all reference tests
pytest tests/reference_test/

```

## Features

- **Flexible Configuration**: YAML-based project configuration with skip support
- **Run or Diff Mode**: Either just run FABulous commands or run + compare outputs
  - **Run** mode checks for command execution errors only and if `expected_outputs` are defined
  - **Diff** Mode copies the project to a temp directory, runs commands, and compares outputs against the original project.
    A project with `rtl_equivalence: true` has its fabric RTL under `Tile/` and `Fabric/` checked with Yosys equivalence instead of a text diff (see below)
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
      A list of glob patterns, which files to diff as text:
      Default include_patterns: ["*.csv", "*.list", "*txt", "*.bin"], plus the project's RTL ("*.v", "*.sv" or "*.vhd", "*.vhdl") unless rtl_equivalence is set
    rtl_equivalence: (Optional)
      Check the RTL with Yosys equivalence instead of a text diff.
      Default rtl_equivalence: false
    exclude_patterns: (Optional) Only for "diff" mode.
      A list of glob patterns, which files to exclude from diff
      Default exclude_patterns: [] # None excluded
    fab_commands: (optional) List of FABulous commands to run.
      Default commands: ["load_fabric", "run_fab"]
    pre_fab_commands: (Optional) List of shell command dicts to run before FABulous commands.
      Each dict supports:
        - cmd: str — the shell command to execute
        - cwd: str | None — subdirectory relative to the project root (default: project root)
        - required_tools: list[str] | None — tools that must be on PATH; command is skipped if any are missing
    post_fab_commands: (Optional) List of shell command dicts to run after FABulous commands.
      Each dict supports:
        - cmd: str — the shell command to execute
        - cwd: str | None — subdirectory relative to the project root (default: project root)
        - required_tools: list[str] | None — tools that must be on PATH; command is skipped if any are missing
    cleanup_commands: (Optional) List of shell command dicts that always run last, even if earlier steps fail.
      Each dict supports:
        - cmd: str — the shell command to execute
        - cwd: str | None — subdirectory relative to the project root (default: project root)
        - required_tools: list[str] | None — tools that must be on PATH; command is skipped if any are missing
    skip_reason: (Optional) Reason to skip this project.
      If provided, the test will be skipped with this reason.
```

### Example Configuration

This is an example configuration for a Verilog project:

```yaml
reference_projects:
  - name: "my_verilog_project"
    path: "./tests/reference_test/projects/my_verilog_project"
    language: "verilog"
    test_mode: "diff" # or "run"
    description: "My custom FABulous project"
    include_patterns: ["*.v", "*.json", "*.csv", "*.txt"] # optional
    exclude_patterns: ["*_test.v", "*.log"] # optional
    expected_outputs: # optional
      - "Fabric/eFPGA_top.v"
      - "Fabric/eFPGA.v"
      - "Tile/LUT4AB/LUT4AB.v"
    fab_commands: #optional
      - "load_fabric"
      - "run_fab"
      - "gen_user_design_wrapper user_design/sequential_16bit_en.v user_design/top_wrapper.v"
      - "compile_design ./user_design/sequential_16bit_en.v"
      - "run_simulation fst ./user_design/sequential_16bit_en.bin"
    post_fab_commands: #optional
      - cmd: "make sim"
        cwd: "Test/"
        required_tools:
          - "yosys"
          - "nextpnr-generic"
          - "iverilog"
    cleanup_commands: #optional, always runs even if earlier steps fail
      - cmd: "make clean"
        cwd: "Test/"
```

## RTL equivalence

`rtl_equivalence_test.py` regenerates every project with `rtl_equivalence: true` and proves its RTL equivalent to the reference with `tests/equivalence.py`, which needs `yosys` on `PATH`, and `ghdl` as well for VHDL projects.
GHDL synthesises a VHDL project to Verilog from its top entity, so VHDL entities outside the top's hierarchy are not compared.
Each side is elaborated with only its own models pack, so a reference project whose pack lacks a cell the generator now emits fails to elaborate.
Every module is proven once as its own top: leaf modules are flattened, and a module that instantiates other project modules keeps those instances as cut points through `expose -evert`.
The instance-to-(type, parameters) map of every module is compared separately, because cutting an instance drops its type.
Instance names must therefore match between the reference and the regenerated RTL.

## Command Line Options

- `--repo-url`: Specify custom GitHub repository URL
- `--projects-dir`: Specify local projects directory
- `--reference-projects-config`: Path to YAML config file

## Examples

```bash
# Test specific project patterns (matches "verilog" in the project names)
pytest tests/reference_test/ -k "verilog"

# Run with custom repository
pytest tests/reference_test/ --repo-url "https://github.com/myuser/my-projects.git"

# Run with custom YAML config
pytest tests/reference_test/ ---reference-projects-config "./test/my_custom_config.yaml"

# Generate pytest report
pytest tests/reference_test/ --html=report.html
```
