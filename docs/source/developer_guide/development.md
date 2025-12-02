(development)=

# Development

This page covers all aspects of contributing to FABulous, including development environment setup, coding standards, and contribution workflows.

(development-env-setup)=

## Development Environment Setup

Contributors must use [uv](https://github.com/astral-sh/uv) for reproducible
environment management and to ensure consistent dependency resolution with CI.

:::{note} Recommended setup for full development (including ASIC backend)
For end-to-end development, including the ASIC backend flow and EDA tooling, use the [Nix-based installation](#nix-install) provided in this repository. Nix ensures the full toolchain (GHDL, Yosys, NextPNR, OpenROAD, Librelane, etc.) is available and reproducible.

Use `uv` alongside Nix for Python-related dependency management of the FABulous project itself (locking, editable installs, tasks), as documented below. The [Dev Container](#dev-container) is available as a fallback when Nix is not accessible, but Nix remains the preferred method whenever possible.
:::

### Installing uv

Linux/macOS:

```console
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your shell or source the `env` snippet the installer prints.

macOS with Homebrew:

```console
brew install uv
```

Windows:

```console
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

PyPI:

```console
pip install uv
```

### Setting up the development environment

Clone the repository and set up the development environment:

```console
git clone https://github.com/FPGA-Research/FABulous
cd FABulous
uv sync --dev                # install runtime + dev dependencies (locked)
uv pip install -e .          # editable install
source .venv/bin/activate    # activate the environment (optional)
```

:::{note}
After running `uv sync`, uv creates a virtual environment in `.venv/`.
You can either:

- Use `uv run <command>` for each command (recommended for reproducibility)
- Activate the environment with `source .venv/bin/activate` and run commands directly
  :::

Common development commands:

```console
# Using uv run:
uv run FABulous -h           # run CLI with project dependencies
uv run pytest               # run test suite
uv run pytest -k test_name  # run specific test
uv run ruff check           # lint code
uv run ruff format          # format code

# Or with activated environment:
(.venv) $ FABulous -h
(.venv) $ pytest
(.venv) $ ruff check
(.venv) $ ruff format
```

Dependency management:

```console
uv add <package>             # add runtime dependency
uv add --group dev <package> # add development dependency
uv remove <package>          # remove dependency
uv lock                      # refresh lock file after manual edits
```

(dev-container)=

## Dev Container (Docker-based Development)

For contributors who prefer a containerized development environment, FABulous provides a pre-configured [Dev Container](https://containers.dev/) setup. This option is intended as a fallback for contributors who cannot use Nix or do not have access to it; Nix remains the preferred method when it is available.

### Working in the Container

Once inside the container, the workspace is mounted at `/workspace`. You can run FABulous commands directly:

```console
FABulous -h                  # run CLI
pytest                       # run test suite
ruff check                   # lint code
ruff format                  # format code
```

:::{note}
The Dev Container uses an editable install, so any changes you make to the FABulous source code are immediately reflected without reinstalling.
:::

### Alternative: Running the Docker Image Directly

If you prefer to use the Docker image without VS Code, you can run it directly:

```console
# Pull the development image
docker pull ghcr.io/fpga-research/fabulous:dev

# Run interactively with your local repo mounted
docker run -it --rm -v $(pwd):/workspace ghcr.io/fpga-research/fabulous:dev
```

(pre-commit)=

## Pre-commit Hooks

We use [pre-commit](https://pre-commit.com/) hooks to maintain code quality.
These hooks automatically run formatters and linters before each commit.

Install pre-commit hooks:

```console
uv run pre-commit install
```

The hooks will now run automatically on `git commit`. You can also run them manually:

```console
uv run pre-commit run --all-files
```

If you need to bypass the hooks temporarily (not recommended):

```console
git commit --no-verify
```

(task-automation)=

## Task Automation with Taskipy

FABulous includes pre-configured [taskipy](https://github.com/taskipy/taskipy) tasks to streamline common development and workflow tasks. After setting up the development environment, you can run these tasks using `task <task-name>`.

### Development and Quality Tasks

```console
task format          # Format code with ruff
task lint            # Lint and fix code issues + run pre-commit
task check           # Check code without fixing
task qa              # Run format and check in sequence
task pre-commit      # Run format and check (for pre-commit hooks)
task ci-check        # Full CI check (format, lint, test, docs)
task install-dev     # Install development dependencies
task clean-all       # Clean all build artifacts and cache files
```

### Documentation Tasks

```console
task docs-setup      # Setup documentation environment
task docs-apidoc     # Generate API documentation only
task docs-build      # Generate API docs + build documentation
task docs-server     # serve docs with live reload for development
task docs-clean      # Clean documentation build artifacts
```

### Project Creation and Setup

```console
task fab-proj               # Create demo project
```

### FABulous Workflow Tasks

```console
# Fabric generation and simulation
task fab-build              # Create demo project + run FABulous fabric generation
task fab-build-clean        # Clean build + create project + run fabric generation
task fab-sim                # Create demo project + run full simulation
task fab-sim-clean          # Clean build + create project + run simulation
```

### Example Development Workflows

**Standard development workflow:**

```console
# Format and check your code
task qa

# Run full CI validation before submitting PR
task ci-check
```

**Quick FABulous testing:**

```console
# Create demo project and test fabric generation
task fab-build

# Run full simulation workflow
task fab-sim
```

**Documentation development:**

```console
# Setup docs environment (first time)
task docs-setup

# Build and serve docs with auto-reload
task docs-server
```

**Clean development environment:**

```console
# Clean all build artifacts and caches
$ task clean-all
```

:::{note}
The taskipy tasks are defined in the `[tool.taskipy.tasks]` section of `pyproject.toml`.
You can view all available tasks by running `task --list` or examine the configuration
in the project's `pyproject.toml` file.
:::

(code-standards)=

## Code Standards

### Code Formatting

We use [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting.
The configuration is defined in `ruff.toml` in the repository root.

Format your code before committing:

```console
uv run ruff format
```

Check for linting issues:

```console
uv run ruff check
uv run ruff check --fix  # auto-fix issues where possible
```

### Documentation Style

- Follow [numpy docstring style](https://numpydoc.readthedocs.io/en/latest/format.html)
- Keep docstrings concise but complete
- Include examples for complex functions
- Update documentation when changing APIs

### Testing

- Write tests for new functionality
- Ensure existing tests pass before submitting PRs
- Run the full test suite: `uv run pytest`
- Check test coverage where applicable

(contribution-workflow)=

## Contribution Workflow

We follow a standard Git workflow for contributions. Please ensure you're familiar with this process before contributing.

### Getting Started

1. Check the [issues](https://github.com/FPGA-Research/FABulous/issues) and the latest commits at the [FABulous main branch](https://github.com/FPGA-Research/FABulous) to see if your feature or bug fix has already been reported or implemented.
2. Fork the repository on GitHub.
3. Clone your forked repository to your local machine.
4. Use the latest version of the `main` branch as base for your work.

### Making Changes

1. Create a new branch for your feature or bug fix:

   ```console
   git checkout -b feature/your-feature-name
   ```

2. Set up the development environment as described above.

3. Make your changes, following the coding standards outlined in this document.

4. Write or update tests as necessary.

5. Ensure all tests pass and code is properly formatted.

6. Commit your changes with clear, descriptive commit messages using the [conventional commits style](https://www.conventionalcommits.org/en/v1.0.0/).

### Submitting Changes

1. Push your changes to your forked repository:

   ```console
   git push origin feature/your-feature-name
   ```

2. Submit a pull request to the main repository.

3. Ensure your pull request targets the `main` branch of the original repository.

4. Check that your pull request passes all CI checks. If it does not, please fix the issues first.

5. We will review your pull request and may request changes or provide feedback. Please be responsive to these requests.

(commit-style)=

### Commit Message Style

We use the [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) style for commit messages and pull requests. This helps us automatically generate changelogs and understand the history of changes better.

Format: `<type>[(<optional scope>)]: <description>`

Examples:

- `feat: add support for new tile type`
- `fix: resolve bitstream generation issue`
- `docs: update installation instructions`
- `test: add integration tests for fabric generator`
- `chore(ci): update workflow`

Types:

- `feat`: new feature
- `fix`: bug fix
- `docs`: documentation changes
- `test`: adding or updating tests
- `refactor`: code refactoring
- `perf`: performance improvements
- `chore`: maintenance tasks

(development-notes)=

## Development Notes

### Environment Management

- **Always use uv for development** to ensure dependency resolution is consistent with CI
- Issues arising only under ad-hoc pip environments may be closed with a request to reproduce under uv
- The `uv.lock` file is the authoritative source for exact dependency versions
- When adding dependencies, prefer adding them via `uv add` rather than manually editing `pyproject.toml`

### Project Structure

- Development dependencies are defined in the `[dependency-groups]` section of `pyproject.toml`
- Regular dependencies are in the `[project]` dependencies list
- Test configuration is in `[tool.pytest.ini_options]` in `pyproject.toml`
- Pre-commit configuration is in `.pre-commit-config.yaml`

### CI/CD

- All pull requests must pass CI checks
- CI runs tests, linting, and formatting checks
- CI uses the same uv-based environment as local development
- Lock file changes are automatically validated

## License

By contributing to this project, you agree that your contributions will be licensed under the project's [Apache 2.0 License](https://opensource.org/licenses/Apache-2.0).
