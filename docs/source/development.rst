.. _Development:

Development
===========

This page covers all aspects of contributing to FABulous, including development environment setup, coding standards, and contribution workflows.

.. _development_env_setup:

Development Environment Setup
-----------------------------

Contributors must use `uv <https://github.com/astral-sh/uv>`_ for reproducible
environment management and to ensure consistent dependency resolution with CI.

Installing uv
~~~~~~~~~~~~~

Linux/macOS:

.. code-block:: console

   $ curl -LsSf https://astral.sh/uv/install.sh | sh
   # restart your shell or source the env snippet the installer prints

macOS with Homebrew:

.. code-block:: console

   $ brew install uv

Windows:

.. code-block:: console

   $ powershell -c "irm https://astral.sh/uv/install.ps1 | iex"


PyPI:

.. code-block:: console

   $ pip install uv



Setting up the development environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Clone the repository and set up the development environment:

.. code-block:: console

   $ git clone https://github.com/FPGA-Research-Manchester/FABulous
   $ cd FABulous
   $ uv sync --dev                # install runtime + dev dependencies (locked)
   $ uv pip install -e .          # editable install
   $ source .venv/bin/activate    # activate the environment (optional)

.. note::

   After running ``uv sync``, uv creates a virtual environment in ``.venv/``.
   You can either:

   - Use ``uv run <command>`` for each command (recommended for reproducibility)
   - Activate the environment with ``source .venv/bin/activate`` and run commands directly

Common development commands:

.. code-block:: console

   # Using uv run (recommended):
   $ uv run FABulous -h           # run CLI with project dependencies
   $ uv run pytest               # run test suite
   $ uv run pytest -k test_name  # run specific test
   $ uv run ruff check           # lint code
   $ uv run ruff format          # format code

   # Or with activated environment:
   (.venv) $ FABulous -h
   (.venv) $ pytest
   (.venv) $ ruff check
   (.venv) $ ruff format

Dependency management:

.. code-block:: console

   $ uv add <package>            # add runtime dependency
   $ uv add --group dev <package> # add development dependency
   $ uv remove <package>         # remove dependency
   $ uv lock                     # refresh lock file after manual edits

.. _pre_commit:

Pre-commit Hooks
----------------

We use `pre-commit <https://pre-commit.com/>`_ hooks to maintain code quality.
These hooks automatically run formatters and linters before each commit.

Install pre-commit hooks:

.. code-block:: console

   $ uv run pre-commit install

The hooks will now run automatically on ``git commit``. You can also run them manually:

.. code-block:: console

   $ uv run pre-commit run --all-files

If you need to bypass the hooks temporarily (not recommended):

.. code-block:: console

   $ git commit --no-verify

.. _task_automation:

Task Automation with Taskipy
-----------------------------

FABulous includes pre-configured `taskipy <https://github.com/taskipy/taskipy>`_ tasks to streamline common development and workflow tasks. After setting up the development environment, you can run these tasks using ``task <task-name>``.

Development and Quality Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   $ task format          # Format code with ruff
   $ task lint            # Lint and fix code issues + run pre-commit
   $ task check           # Check code without fixing
   $ task qa              # Run format and check in sequence
   $ task pre-commit      # Run format and check (for pre-commit hooks)
   $ task ci-check        # Full CI check (format, lint, test, docs)
   $ task install-dev     # Install development dependencies
   $ task clean-all       # Clean all build artifacts and cache files

Documentation Tasks
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   $ task docs-setup      # Setup documentation environment
   $ task docs-apidoc     # Generate API documentation only
   $ task docs-build      # Generate API docs + build documentation
   $ task docs-serve      # Serve docs with live reload for development
   $ task docs-clean      # Clean documentation build artifacts

Project Creation and Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   $ task fab-proj               # Create demo project

FABulous Workflow Tasks
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Fabric generation and simulation
   $ task fab-build              # Create demo project + run FABulous fabric generation
   $ task fab-build-clean        # Clean build + create project + run fabric generation
   $ task fab-sim                # Create demo project + run full simulation
   $ task fab-sim-clean          # Clean build + create project + run simulation

Example Development Workflows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Standard development workflow:**

.. code-block:: console

   # Format and check your code
   $ task qa

   # Run full CI validation before submitting PR
   $ task ci-check

**Quick FABulous testing:**

.. code-block:: console

   # Create demo project and test fabric generation
   $ task fab-build

   # Run full simulation workflow
   $ task fab-sim

**Documentation development:**

.. code-block:: console

   # Setup docs environment (first time)
   $ task docs-setup

   # Build and serve docs with auto-reload
   $ task docs-serve

**Clean development environment:**

.. code-block:: console

   # Clean all build artifacts and caches
   $ task clean-all

.. note::

   The taskipy tasks are defined in the ``[tool.taskipy.tasks]`` section of ``pyproject.toml``.
   You can view all available tasks by running ``task --list`` or examine the configuration
   in the project's ``pyproject.toml`` file.

.. _code_standards:

Code Standards
--------------

Code Formatting
~~~~~~~~~~~~~~~

We use `Ruff <https://docs.astral.sh/ruff/>`_ for both linting and formatting.
The configuration is defined in ``ruff.toml`` in the repository root.

Format your code before committing:

.. code-block:: console

   $ uv run ruff format

Check for linting issues:

.. code-block:: console

   $ uv run ruff check
   $ uv run ruff check --fix  # auto-fix issues where possible

Documentation Style
~~~~~~~~~~~~~~~~~~~

- Follow `numpy docstring style <https://numpydoc.readthedocs.io/en/latest/format.html>`_
- Keep docstrings concise but complete
- Include examples for complex functions
- Update documentation when changing APIs

Testing
~~~~~~~

- Write tests for new functionality
- Ensure existing tests pass before submitting PRs
- Run the full test suite: ``uv run pytest``
- Check test coverage where applicable

.. _contribution_workflow:

Contribution Workflow
---------------------

We follow a standard Git workflow for contributions. Please ensure you're familiar with this process before contributing.

Getting Started
~~~~~~~~~~~~~~~

1. Check the `issues <https://github.com/FPGA-Research-Manchester/FABulous/issues>`_ and `FABulous development branch <https://github.com/FPGA-Research/FABulous/tree/FABulous2.0-development>`_ to see if your feature or bug fix has already been reported or implemented.

2. Fork the repository on GitHub.

3. Clone your forked repository to your local machine.

4. If you are not already on the ``FABulous2.0-development`` branch, switch to it to use it as base for your work.


Making Changes
~~~~~~~~~~~~~~

1. Create a new branch for your feature or bug fix:

   .. code-block:: console

      $ git checkout -b feature/your-feature-name

2. Set up the development environment as described above.

3. Make your changes, following the coding standards outlined in this document.

4. Write or update tests as necessary.

5. Ensure all tests pass and code is properly formatted.

6. Commit your changes with clear, descriptive commit messages using the `conventional commits style <https://www.conventionalcommits.org/en/v1.0.0/>`_.

Submitting Changes
~~~~~~~~~~~~~~~~~~

1. Push your changes to your forked repository:

   .. code-block:: console

      $ git push origin feature/your-feature-name

2. Submit a pull request to the main repository.

3. Ensure your pull request targets the ``FABulous2.0-development`` branch of the original repository.

4. Check that your pull request passes all CI checks. If it does not, please fix the issues first.

5. We will review your pull request and may request changes or provide feedback. Please be responsive to these requests.

.. _commit_style:

Commit Message Style
~~~~~~~~~~~~~~~~~~~~

We use the `conventional commits <https://www.conventionalcommits.org/en/v1.0.0/>`_ style for commit messages and pull requests. This helps us automatically generate changelogs and understand the history of changes better.

Format: ``<type>[optional scope]: <description>``

Examples:

.. code-block:: text

   feat: add support for new tile type
   fix: resolve bitstream generation issue
   docs: update installation instructions
   test: add integration tests for fabric generator
   refactor: simplify switch matrix generation

Types:
- ``feat``: new feature
- ``fix``: bug fix
- ``docs``: documentation changes
- ``test``: adding or updating tests
- ``refactor``: code refactoring
- ``perf``: performance improvements
- ``chore``: maintenance tasks

.. _development_notes:

Development Notes
-----------------

Environment Management
~~~~~~~~~~~~~~~~~~~~~~

- **Always use uv for development** to ensure dependency resolution is consistent with CI
- Issues arising only under ad-hoc pip environments may be closed with a request to reproduce under uv
- The ``uv.lock`` file is the authoritative source for exact dependency versions
- When adding dependencies, prefer adding them via ``uv add`` rather than manually editing ``pyproject.toml``

Project Structure
~~~~~~~~~~~~~~~~~

- Development dependencies are defined in the ``[dependency-groups]`` section of ``pyproject.toml``
- Regular dependencies are in the ``[project]`` dependencies list
- Test configuration is in ``[tool.pytest.ini_options]`` in ``pyproject.toml``
- Pre-commit configuration is in ``.pre-commit-config.yaml``

CI/CD
~~~~~

- All pull requests must pass CI checks
- CI runs tests, linting, and formatting checks
- CI uses the same uv-based environment as local development
- Lock file changes are automatically validated

License
-------

By contributing to this project, you agree that your contributions will be licensed under the project's `Apache 2.0 License <https://opensource.org/licenses/Apache-2.0>`_.
