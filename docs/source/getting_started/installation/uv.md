(uv-install)=
# `uv` based setup

[uv](https://github.com/astral-sh/uv) is a high-performance Python package manager that provides faster dependency resolution and installation. While not required for end users, it offers significant speed improvements and reproducible environments.

## Installing uv

Linux/macOS:

```bash
$ curl -LsSf https://astral.sh/uv/install.sh | sh
# restart your shell or source the env snippet the installer prints
```

macOS with Homebrew:

```bash
brew install uv
```

Windows:

```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

PyPI:

```bash
pip install uv
```

## Install and run FABulous

To install FABulous run:

```bash
uv sync
```

After the installation you can use can simply replace anything you want to run and pre-pend it with `uv run`. For example `uv run FABulous`. If you want to avoid keep typing `uv run` you can do `source .venv/bin/activate` and this will activate the virtual environment, and everything will run under `uv`.
