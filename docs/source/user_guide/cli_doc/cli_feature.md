# FABulous CLI — Features and Usage

In FABulous, we provide two primary methods to drive the tool. First is the interactive REPL mode, which is good for performing design space exploration. Second is the batch mode, which is good for CI and automation. This document summarizes the key features of both modes and provides guidance on when to use each.

## Interactive mode

To start the REPL, simply run `FABulous start`, which will launch the interactive shell in the current working directory.

```bash
FABulous start

# you will see a prompt like this:
FABulous>
```

If you want to start the REPL for a specific project directory, you can do this by providing the `--project-dir/-p` arguments to choose which project directory to load (`FABulous -p <my_project> start`).

Once you are in the REPL, you will find many features that help you with the flow.
You can type `help` or `?` in the REPL to see a list of all available commands and their descriptions.
We will list out a few useful ones below. For more details on the capabilities of `cmd2`, please refer to the [cmd2 documentation](https://cmd2.readthedocs.io/en/stable/) since FABulous CLI is built on top of `cmd2`.

For more details about the available commands, please refer to the [Interactive CLI Commands Reference](#interactive-cli-commands-reference).

### Session variables

- `set <name> <value>` / `get <name>` (`cmd2` Settable integration).

```bash
FABulous> set projectDir /path/to/project
FABulous> get projectDir
/path/to/project
```

### Persistent history and recall

History is stored under `.FABulous/.fabulous_history`. Use `history` to list entries and `!<n>` or `!<prefix>` to re-run commands.

### Tab completion

Argument and filesystem completion are available — press Tab to complete filenames and subcommands.

### Editor integration (`edit`)

You can open files from the REPL in your preferred editor and return to the CLI once the editor closes. The CLI chooses the editor from the following (in order): the environment variable `FABULOUS_EDITOR` (recommended), then `EDITOR` / `VISUAL`.
The main use of the `FABULOUS_EDITOR` is to provide per-project editor settings, but without it, the CLI will try resolving with the `$EDITOR` which is set for most terminal environments.

For more details on FABulous environment variables, see [FABulous environment variables](#fabulous-variables).

Examples:

```bash
# Start FABulous with VS Code as the editor (example for a code --wait invocation)
FABULOUS_EDITOR="/usr/bin/code --wait" FABulous start
FABulous> edit Fabric/myfabric_top.v
```

### Macros, shortcuts, aliases (quick automation)

cmd2 supplies powerful interactive automation helpers:

- Macros: record sequences of CLI commands and replay them as a single named item.
- Shortcuts: map a short token to a longer command prefix so you can type less.
- Aliases: create command synonyms (useful for long or frequently used commands).

Common workflows (examples — exact subcommand names may differ slightly depending on cmd2 version):

1) Creating a macro (interactive):

```text
FABulous> macro create mybuild
Enter commands to store in the macro (blank line to finish):
load_fabric
gen_fabric
gen_top_wrapper

Macro 'mybuild' created.
```

Then run the macro by name:

```text
FABulous> macro run mybuild
```

2) Shortcuts (quick token expansion):

```text
FABulous> shortcut add gfg "gen_fabric; gen_top_wrapper"
FABulous> gfg
```

3) Aliases (persistent command synonyms):

```text
FABulous> alias add gf gen_fabric
FABulous> gf
```

Useful commands to inspect and manage automation helpers:

- `history` — view previous commands and save ranges to a script.
- `macros` / `aliases` / `shortcuts` (or `macro list`) — list configured items.
- `macro delete NAME`, `alias delete NAME`, `shortcut delete NAME` — remove items.

### Shell integration (`shell` / `!`)

Use `shell <command>` or the shorthand `!<command>` to execute an operating-system command from the CLI. This is handy for quick filesystem checks or invoking tools (e.g. `ls`, `git`, `make`).

Examples:

```text
FABulous> shell ls -la Tile/
FABulous> !git status
```

Notes:

- `shell` runs commands in a subprocess and returns control when they finish. The CLI captures the return code in `last_result` which can be inspected by pyscripts or by checking `$?`-like semantics in your environment.
- Use `!` for convenience; `shell` is clearer in scripts.

### Script execution (`run_script`, transcripts)

`run_script <file>` executes a plain-text script where each line is a CLI command. This is the recommended way to record sequences you want to run unchanged across environments or CI runs, because `run_script` respects the CLI's parsing, hooks, and safety features.

Example `fab_build.fab` (text script of FABulous commands):

```
load_fabric
gen_all_tile
gen_fabric
gen_bitStream_spec
gen_top_wrapper
```

Run it:

```text
FABulous> run_script fab_build.fab
```

## Python scripting with cmd2

Prefer using text scripts and pyscripts for automation and reproducible runs. These two approaches are the recommended, supported ways to drive FABulous via its CLI:

- Text scripts (plain CLI commands) — use `run_script <file>` to execute a file containing one CLI command per line. This is the simplest, most portable approach and works well for CI, demos, and reproducible workflows.
- Python scripts / pyscripts — use `run_pyscript <file>` to run Python code inside the CLI process. Pyscripts get a small helper called `app` (the PyBridge) injected into their locals so they can call CLI commands and capture outputs programmatically.

Text script example (fab_build.fab):

```text
load_fabric
gen_all_tile
gen_fabric
gen_bitStream_spec
gen_top_wrapper
```

Run it from the FABulous prompt:

```text
FABulous> run_script fab_build.fab
```

### Pyscript notes and example

Key points about pyscripts:

- Run a pyscript from the FABulous shell with: `run_pyscript my_script.py`.
- Inside the pyscript an `app(...)` callable is available. Calling `app('some command')` runs that command using the same parsing and hooks as the REPL and returns a `CommandResult` namedtuple with `stdout`, `stderr`, `stop`, and `data` fields.
- `sys.argv` will be set for the pyscript (so you can parse script arguments). The script runs with `__name__ == '__main__'` and the script directory is temporarily added to `sys.path` just like regular Python script execution.
- By default the CLI exposes the raw `self` (CLI instance) into pyscript locals, which allows you to call the stable `FABulous_API` for direct API access and access the internal state of the CLI.

Minimal pyscript example (`my_pipeline.py`):

```python
# my_pipeline.py
# Called with: FABulous> run_pyscript my_pipeline.py --arg1 value

res = app('load_fabric')           # run a CLI command and capture result
print('load_fabric stdout:', res.stdout)
if not res:
    print('load_fabric failed:', res.stderr)

# run a compound command and inspect return data (commands can populate app.last_result)
result = app('gen_fabric')
print('gen_fabric returned stop=', result.stop)
print('gen_fabric data=', result.data)

import sys
print('script argv:', sys.argv)
```

## Batch Mode

Since running a written script or doing automation within a CI is very common, we also offer batch mode to directly run scripts and commands using the `FABulous` command.

A very common use case is to compile a fabric which can be done by doing the following:

```bash
FABulous run "load_fabric; run_FABulous_fabric"
```

Which will load the fabric and generate the fabric RTL code. By default, if any command in the sequence fails, execution stops immediately and returns a non-zero exit code. To continue execution despite errors, use the `--force` flag.

Similarly, you can also run a script file directly by doing:

```bash
# fabulous text script
FABulous script script.fab

# fabulous tcl script
FABulous script script.tcl

# python script
FABulous script script.py
```

TCL scripts are fully supported and can use standard TCL syntax — all FABulous CLI commands are registered as TCL commands, so you can use them as if they were normal TCL procedures.

We have included some simple logic to determine the script type based on the file extension (`.fab`/`.fs` for FABulous scripts, `.tcl` for TCL, `.py` for Python), but if desired you can also explicitly specify the script type by using the `--type` argument.

The `FABulous` tool can also do more than just starting the shell and running scripts. For more details of what it is capable of, please refer to the `FABulous --help` output.
