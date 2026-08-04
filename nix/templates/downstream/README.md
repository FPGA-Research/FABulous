# A project built on FABulous

This template wires a chip or fabric project to FABulous through Nix.

```bash
nix develop
```

That gives you the `FABulous` and `librelane` CLIs, the full EDA toolchain
(Yosys with the GHDL plugin, nextpnr, OpenROAD, GHDL), and a Python environment
holding FABulous plus whatever you list in `extra-python-packages`.

## Adding Python packages

`extra-python-packages` selects from `pkgs.fabulous-python`, an ordinary nixpkgs
Python interpreter whose package set is FABulous's `uv.lock`. A package you pick
there is built against the same versions FABulous itself runs on, so a shared
dependency is one build rather than two competing copies.

```nix
extra-python-packages = ps: [ ps.cocotb ps.pytest ps.numpy ];
```

Because it is a normal nixpkgs Python set, it composes normally too:

```nix
pkgs.fabulous-python.withPackages (ps: [ ps.fabulous-fpga ])   # a bare env
pkgs.fabulous-python.pkgs.fabulous-fpga                        # a dependency
```

## Upgrading

```bash
nix flake update fabulous
```

FABulous's Python versions come from its `uv.lock`, and the EDA toolchain from
its flake inputs, so one update moves both.

## If you need your own uv.lock

Should this project grow Python dependencies that FABulous's lock does not
resolve, or need a version it pins differently, build a virtualenv from your own
`uv.lock` and pass it as `python-env`. See _Bringing your own uv.lock_ in the
FABulous Nix documentation.

## Known limitations

The `librelane_plugin_fabulous` GDS plugin ships in the FABulous wheel from
2.2.0 onwards. On an older FABulous everything else works, but `librelane` will
not discover the FABulous flows.

FABulous installs both a `FABulous` and a `fabulous` command. On a
case-insensitive `/nix` those are one path, so only one file survives and which
name it carries depends on the installer; lookup is case-insensitive there too,
so both commands still work. The Nix installer creates a case-sensitive store
volume on macOS by default, so this normally does not arise at all.
