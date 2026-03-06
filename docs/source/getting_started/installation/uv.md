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

## Install FABulous

Install FABulous as a tool so the `FABulous` command is available globally:

```bash
uv tool install fabulous-fpga
```

Verify the installation:

```bash
FABulous --version
```

To upgrade later:

```bash
uv tool upgrade fabulous-fpga
```
