# The shell FABulous development and downstream chip projects both build on.
#
# Mirrors `librelane-shell`'s composition surface, so a project that already
# knows how to extend a librelane shell needs no new vocabulary:
#
#   pkgs.fabulous-shell.override {
#     extra-packages = [ pkgs.iverilog ];
#     extra-python-packages = ps: [ ps.cocotb ];
#   }
#
# `extra-python-packages` selects from `fabulous-python`'s package set, which is
# uv.lock's. A package chosen there is resolved against the same versions
# FABulous itself runs on, so there is no PYTHONPATH precedence to reason about
# and no second copy of a shared dependency.
{
  lib,
  devshell,
  # The interpreter whose package set is uv.lock's.
  fabulous-python,
  fabulous,
  extra-packages ? [ ],
  extra-python-packages ? (ps: [ ]),
  # The environment to put on PATH. Defaults to FABulous plus whatever the
  # caller asked for, built from `fabulous-python`. This repo's own `devShells`
  # replace it wholesale with an editable uv2nix virtualenv, which is the one
  # thing the converted set cannot express: `toNixpkgs` builds from wheels, and
  # a wheel is by definition not an editable checkout.
  python-env ? fabulous-python.withPackages (
    ps:
    [
      ps.fabulous-fpga
      ps.tkinter
    ]
    ++ extra-python-packages ps
  ),
  # Extra site-packages directories to prepend. Only needed alongside a
  # `python-env` that is a uv2nix virtualenv, whose interpreter has no tkinter.
  extra-python-path ? [ ],
  extra-env ? [ ],
  # Repository checkout to make importable, for editable installs. Null for the
  # hermetic consumer shell, which has no checkout to resolve against.
  editable-root ? null,
  # Generate `librelane_plugin_fabulous` into $REPO_ROOT on startup. Only ever
  # true for an editable checkout *of this repo*: the hook imports FABulous's
  # own `build_hooks`, which no downstream checkout has. A downstream venv gets
  # the plugin from the wheel instead.
  materialize-plugin ? false,
  # Additional `devshell.startup` / `devshell.interactive` entries. Used by this
  # repo's own shells; downstream projects should not need them.
  extra-startup ? { },
  extra-interactive ? { },
}:

assert lib.assertMsg (!materialize-plugin || editable-root != null)
  "fabulous-shell: materialize-plugin needs editable-root — the plugin is generated into $REPO_ROOT.";

let
  inherit (fabulous.passthru) includedTools;

  # `python-env` puts its own site-packages on the interpreter's path, so
  # nothing has to be reconstructed here. Only the extras a virtualenv-shaped
  # env cannot carry get prepended, and the checkout is deliberately absent:
  # it is known only once the startup hook has resolved $REPO_ROOT.
  pythonPath = lib.concatStringsSep ":" extra-python-path;

  # `librelane_plugin_fabulous` is generated at build time. pip/uv build from
  # the checkout, so an editable install writes it straight there; Nix builds in
  # a sandboxed copy of the source that is discarded, leaving nothing for the
  # editable finder to import. Generate it on startup instead.
  materializePlugin = lib.optionalString materialize-plugin ''
    if [ -w "$REPO_ROOT" ]; then
      python -c "import sys; sys.path.insert(0, '$REPO_ROOT'); import build_hooks; build_hooks.materialize_librelane_plugin()"
    fi
  '';

  prompt = ''\[\033[1;32m\][FABulous-nix:\w]\$\[\033[0m\] '';
in

devshell.mkShell {
  devshell.packages = [ python-env ] ++ includedTools ++ extra-packages;

  # Taken wholesale from `fabulous.passthru.env` rather than re-spelled, so a
  # variable added to the wrapper's runtime environment reaches every shell
  # built from here instead of silently applying to only one of the two.
  env =
    lib.mapAttrsToList (name: value: { inherit name value; }) (
      fabulous.passthru.env
      // {
        PYTHONPATH = pythonPath;
        PYTHONNOUSERSITE = "1";
        UV_NO_SYNC = "1";
        UV_PYTHON = "${python-env}/bin/python";
        UV_PYTHON_DOWNLOADS = "never";
      }
    )
    ++ extra-env;

  devshell.startup = {
    fabulous-setup.text = lib.optionalString (editable-root != null) ''

      # The editable install resolves fabulous/ and the generated side-packages
      # under $REPO_ROOT, so it has to be the developer's checkout. Only when
      # there is none (e.g. `nix develop github:...`) does it fall back to the
      # read-only flake source in /nix/store.
      if [ -z "''${REPO_ROOT:-}" ]; then
        export REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "${editable-root}")"
      fi
      export PYTHONPATH="$PYTHONPATH:$REPO_ROOT"
      ${materializePlugin}
    '';
  }
  // extra-startup;

  devshell.interactive = {
    PS1.text = ''PS1="${prompt}"'';
  }
  // extra-interactive;

  motd = "";
}
