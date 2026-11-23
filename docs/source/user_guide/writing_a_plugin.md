# Writing a FABulous plugin

A plugin adds features to FABulous without changing FABulous itself. A plugin
can:

- add commands to the FABulous shell;
- run code when FABulous starts or when a fabric is loaded;
- declare its own settings;
- add an HDL code generator, a fabric file parser, or a place-and-route model
  backend.

This page first walks through building a small plugin step by step, then lists
everything a plugin can provide. You only need to know Python to follow it.

## How a plugin works

A plugin is an ordinary Python module or package. FABulous imports it and looks
for two things:

- **`FABULOUS_PLUGIN_API`**, a module-level constant set to
  `PLUGIN_API_VERSION`. It records which version of the plugin interface the
  plugin was written for. FABulous refuses to load a plugin that lacks it or
  declares a different version, so an outdated plugin fails at startup instead
  of half-way through a flow.
- **Hook functions**, which are functions decorated with `@hookimpl`. FABulous
  calls them at fixed points. Which point depends only on the function's name:
  a function called `fabulous_register_commands` is called when the shell
  collects its commands. The [hook reference](#hook-reference) lists every name.

A hook function's name must match a hook exactly. A misspelled name is an error
that names your plugin, rather than a hook that silently never runs.

FABulous looks for plugins in four places, in this order:

| Where | Use it for |
| --- | --- |
| Built into FABulous | the default Verilog/VHDL generators, the fabric parsers, and the nextpnr model |
| `plugins/` in your project | plugins that belong to one project |
| installed Python packages that declare a `fabulous.plugins` entry point | plugins you share or reuse across projects |
| `--plugin`/`-m` on the command line | trying out a plugin for one session |

The `plugins/` directory can be changed with the `FAB_PLUGIN_DIR` setting. A
relative path is resolved against the project directory.

## Tutorial: a `hello` plugin

This tutorial builds a plugin that adds a `hello` command, reports the size of
each fabric that is loaded, and lets the user configure its greeting.

### Step 1: create an empty plugin

Create a project, if you do not have one yet, and a package for the plugin in
its `plugins/` directory:

```bash
FABulous create-project demo
cd demo
mkdir -p plugins/hello
```

Create `plugins/hello/__init__.py` with only the version declaration:

```python
from fabulous.plugins import PLUGIN_API_VERSION

FABULOUS_PLUGIN_API = PLUGIN_API_VERSION
```

This is already a valid plugin, although it does nothing yet. Check that
FABulous finds it:

```console
$ FABulous plugins list
Plugins:
  name                                               tier   version
  fabulous.fabric_cad.plugin                         core   ...
  fabulous.fabric_generator.code_generator.plugin    core   ...
  fabulous.fabric_generator.parser.plugin            core   ...
  hello                                              plugin unknown
```

The version shows `unknown` because a directory plugin has no package metadata.
It shows a real version once the plugin is packaged in step 5.

### Step 2: add a command

Shell commands are [cmd2](https://cmd2.readthedocs.io/) commands. Write a
`CommandSet` subclass whose `do_<name>` methods are the commands, and return an
instance of it from the `fabulous_register_commands` hook:

```python
from typing import ClassVar

from cmd2 import CommandSet

from fabulous.plugins import PLUGIN_API_VERSION, hookimpl

FABULOUS_PLUGIN_API = PLUGIN_API_VERSION


class HelloCommands(CommandSet):
    DEFAULT_CATEGORY: ClassVar[str] = "Hello"

    def do_hello(self, _statement: object) -> None:
        """Greet the user."""
        self._cmd.poutput("Hello from my first plugin!")


@hookimpl
def fabulous_register_commands():
    return HelloCommands()
```

Run the command:

```console
$ FABulous run hello
Hello from my first plugin!
```

The command is also available in the interactive shell (`FABulous start`),
where `help hello` shows its docstring, and in Tcl scripts.

### Step 3: react when a fabric is loaded

The `fabulous_after_fabric_loaded` hook runs every time a fabric is loaded. It
receives the `FABulous_API` instance, whose `fabric` attribute holds the loaded
fabric. Add it to the same file:

```python
from loguru import logger


@hookimpl
def fabulous_after_fabric_loaded(api):
    fabric = api.fabric
    logger.info(
        f"hello: loaded '{fabric.name}', "
        f"{fabric.numberOfRows} rows x {fabric.numberOfColumns} columns"
    )
```

FABulous loads the project's fabric when it starts, so the message appears
before your command's output:

```console
$ FABulous run hello
INFO | hello: loaded 'eFPGA', 16 rows x 10 columns
Hello from my first plugin!
```

A hook function may leave out arguments it does not need. If you only want to
know that a fabric was loaded, `def fabulous_after_fabric_loaded():` works as
well.

### Step 4: make it configurable

Declare the plugin's settings as a subclass of `PluginSettings`, which is a
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
model, and return the class from the `fabulous_register_settings` hook. `group`
is the name the settings are stored under. `env_prefix` must be `FAB_`, then
the group in capitals, then two underscores; FABulous refuses to load settings
with any other prefix, because `FAB_` alone belongs to FABulous's own settings:

```python
from pydantic_settings import SettingsConfigDict

from fabulous.fabulous_settings import PluginSettings


class HelloSettings(PluginSettings):
    group = "hello"
    model_config = SettingsConfigDict(env_prefix="FAB_HELLO__")
    greeting: str = "Hello"


@hookimpl
def fabulous_register_settings():
    return HelloSettings
```

Read the settings with `HelloSettings.from_context()`. Update the command to use
the greeting:

```python
    def do_hello(self, _statement: object) -> None:
        """Greet the user."""
        greeting = HelloSettings.from_context().greeting
        self._cmd.poutput(f"{greeting} from my first plugin!")
```

Each field is set by a variable named after the prefix and the field. Like
FABulous's own settings, it can go in the project's `.FABulous/.env` file:

```console
$ echo "FAB_HELLO__GREETING=Servus" >> .FABulous/.env
$ FABulous run hello
Servus from my first plugin!
```

An environment variable of the same name overrides the `.env` file for one run:

```console
$ FAB_HELLO__GREETING=Hi FABulous run hello
Hi from my first plugin!
```

`FABulous plugins info hello` now shows the settings group and its prefix.

### Step 5: package and share it

To use the plugin in other projects, or to share it, turn it into an
installable Python package. The quickest start is the
[FABulous plugin template](https://github.com/FPGA-Research/fabulous-plugin-template):
create a repository from it, then rename its package and entry point.

To do it by hand, move the code into a package, here `src/fabulous_hello/__init__.py`,
and add a `pyproject.toml` that declares a `fabulous.plugins` entry point:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "fabulous-hello"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["FABulous-FPGA"]

[project.entry-points."fabulous.plugins"]
hello = "fabulous_hello"
```

The entry point's name (`hello`) is the plugin's name in FABulous, and its value
is the module FABulous imports. That module must declare `FABULOUS_PLUGIN_API`.
Delete the `plugins/hello` copy from the project, so the project and the
package do not both register the same command, then install the package into
the environment FABulous runs in:

```console
$ FABulous plugins install ./fabulous-hello
Installed. Added plugin(s): hello.
```

`plugins install` takes anything `uv pip install` accepts, including a git URL.
The plugin is available from the next FABulous session, and
`FABulous plugins list` now shows its version. Remove it with
`FABulous plugins uninstall fabulous-hello`, which takes the package name.

### Trying a plugin without installing it

`--plugin` (short `-m`) loads a plugin for a single session. It is an option of
`start`, `run` and `script`, can be repeated, and takes either a directory that
contains an `__init__.py` or a dotted module name:

```bash
FABulous -p demo start -m ./fabulous-hello/src/fabulous_hello
```

A plugin loaded this way must still declare `FABULOUS_PLUGIN_API`.

## Hook reference

| Hook | Called | Return |
| --- | --- | --- |
| `fabulous_register_commands()` | when the shell starts | a cmd2 `CommandSet`, a list of them, or `None` |
| `fabulous_register_settings()` | after discovery | your `PluginSettings` subclass, or `None` |
| `fabulous_startup()` | once, when the shell starts | nothing |
| `fabulous_after_fabric_loaded(api)` | after each fabric load | nothing |
| `fabulous_register_code_generators()` | after discovery | a list of `CodeGeneratorProvider` |
| `fabulous_register_parsers()` | after discovery | a list of `ParserProvider` |
| `fabulous_register_pnr_models()` | after discovery | a list of `PnRModelProvider` |

The provider classes are in `fabulous.plugins.types`. Each one is keyed: code
generators by `HDLType`, parsers by file suffix, and place-and-route models by
tool name. Two plugins providing the same key is an error that names both.

### Code generators and parsers

A `CodeGeneratorProvider` gives the HDL language it produces and a `factory`
that builds the generator. A `ParserProvider` gives the fabric file suffix it
reads and a `parse` function that turns that file into a `Fabric`:

```python
from fabulous.plugins import hookimpl
from fabulous.plugins.types import ParserProvider


def parse_my_format(path):
    ...  # build and return a fabulous.fabric_definition.fabric.Fabric


@hookimpl
def fabulous_register_parsers():
    return [ParserProvider(suffix=".myfab", parse=parse_my_format, name="my-format")]
```

`load_fabric fabric.myfab` then reads the fabric with your parser.

### Place-and-route model backends

`fabulous_register_pnr_models` contributes a way to describe the fabric to a
place-and-route tool. A provider is keyed by tool name, and `generate` returns
the whole model as a mapping of file name to file content, so your backend
decides how many files it emits and what they are called:

```python
from fabulous.plugins import PLUGIN_API_VERSION, hookimpl
from fabulous.plugins.types import PnRModelProvider

FABULOUS_PLUGIN_API = PLUGIN_API_VERSION


def generate_my_model(fabric, delay_model=None, target=None) -> dict[str, str | bytes]:
    return {"arch.xml": build_arch_xml(fabric, delay_model, target)}


@hookimpl
def fabulous_register_pnr_models() -> list[PnRModelProvider]:
    return [
        PnRModelProvider(
            tool="my_router",
            generate=generate_my_model,
            supports_timing=True,
            name="my-router",
        )
    ]
```

File names may include subdirectories, but must stay inside the output
directory. FABulous rejects the whole model before writing anything if one name
points outside it.

Set `supports_timing` to `False` if `generate` cannot use a delay model.
FABulous then refuses a timed generation for your backend rather than silently
producing an untimed model. Nothing outside your backend knows how the delays
are embedded, so a backend may put them inline, in a sidecar file or in a binary
database. With a delay model, `target` (a `TimingModelTarget`) says whether pip
delays, BEL delays, or both should be characterized.

Select a backend with the `pnr_backend` setting, or for one run with
`gen_routing_model --backend my_router`. Built-in tool names live in the `PnRTool`
enum; a plugin may register any name that is not already taken.

## When a plugin breaks

By default a plugin that fails stops FABulous with an error that names it. This
covers a plugin that fails to import, declares a different
`FABULOUS_PLUGIN_API`, misspells a hook, or raises inside a hook.

With `--skip-broken-plugins` (or `FAB_SKIP_BROKEN_PLUGINS=true`), FABulous
instead logs a warning and unregisters only the broken plugin. Everything that
plugin had already registered is removed too, and the built-in features and
every other plugin keep working.
