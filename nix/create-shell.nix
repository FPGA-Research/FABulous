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
  # `ps: [ ... ]`, selected from `fabulous-python`.
  extra-python-packages ? null,
  # A complete environment in place of FABulous plus `extra-python-packages`,
  # such as a uv2nix virtualenv. An editable checkout needs one, because
  # `toNixpkgs` builds from wheels and a wheel is not an editable checkout.
  python-env ? null,
  extra-env ? [ ],
  # Repository checkout to make importable, for editable installs. Null for the
  # hermetic consumer shell, which has no checkout to resolve against.
  editable-root ? null,
  # Generate `librelane_plugin_fabulous` into a FABulous source checkout at
  # $REPO_ROOT on startup. An installed wheel already carries the plugin.
  materialize-plugin ? false,
  # Additional `devshell.startup` / `devshell.interactive` entries.
  extra-startup ? { },
  extra-interactive ? { },
}:

assert lib.assertMsg (!materialize-plugin || editable-root != null)
  "fabulous-shell: materialize-plugin needs editable-root, because the plugin is generated into $REPO_ROOT.";
assert lib.assertMsg (python-env == null || extra-python-packages == null)
  "fabulous-shell: extra-python-packages has no effect when python-env is given. Add the packages to python-env instead.";

let
  pythonEnv =
    if python-env != null then
      python-env
    else
      fabulous-python.withPackages (
        ps: [ ps.fabulous-fpga ] ++ lib.optionals (extra-python-packages != null) (extra-python-packages ps)
      );

  inherit (fabulous.passthru) includedTools;

  # The FABulous CLI imports tkinter at startup, and neither a uv.lock nor a
  # uv2nix virtualenv can carry it, so the shell supplies it for any
  # `python-env`. The checkout is appended by the startup hook once $REPO_ROOT
  # is known.
  tkinterPath = "${fabulous-python.pkgs.tkinter}/${fabulous-python.sitePackages}";

  # `librelane_plugin_fabulous` is generated at build time. pip/uv build from
  # the checkout, so an editable install writes it straight there; Nix builds in
  # a sandboxed copy of the source that is discarded, leaving nothing for the
  # editable finder to import. Generate it on startup instead. Skipped for the
  # read-only store copy and for an installed wheel's site-packages, which
  # `FABulous nix-env` passes as $REPO_ROOT and which has no `build_hooks.py`.
  materializePlugin = lib.optionalString materialize-plugin ''
    if [ -w "$REPO_ROOT" ] && [ -f "$REPO_ROOT/build_hooks.py" ]; then
      python -c "import sys; sys.path.insert(0, '$REPO_ROOT'); import build_hooks; build_hooks.materialize_librelane_plugin()"
    fi
  '';

  prompt = ''\[\033[1;32m\][FABulous-nix:\w]\$\[\033[0m\] '';
in

devshell.mkShell {
  devshell.packages = [ pythonEnv ] ++ includedTools ++ extra-packages;

  # Taken wholesale from `fabulous.passthru.env` rather than re-spelled, so a
  # variable added to the wrapper's runtime environment reaches every shell
  # built from here instead of silently applying to only one of the two.
  env =
    lib.mapAttrsToList (name: value: { inherit name value; }) (
      fabulous.passthru.env
      // {
        PYTHONNOUSERSITE = "1";
        UV_NO_SYNC = "1";
        UV_PYTHON = "${pythonEnv}/bin/python";
        UV_PYTHON_DOWNLOADS = "never";
      }
    )
    ++ [
      {
        name = "PYTHONPATH";
        # A consumer shell keeps the caller's PYTHONPATH. An editable shell
        # replaces it, because `FABulous nix-env` is entered from a shell that
        # may carry another Python's paths.
        eval =
          if editable-root == null then
            ''"${tkinterPath}''${PYTHONPATH:+:$PYTHONPATH}"''
          else
            ''"${tkinterPath}"'';
      }
    ]
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
      # $LIBRELANE_EXTRA_PYTHONPATH is read at shell startup so out-of-tree
      # librelane_plugin_* trees stay discoverable. builtins.getEnv at eval time
      # is always empty under the flake's pure evaluation.
      export PYTHONPATH="$PYTHONPATH:$REPO_ROOT''${LIBRELANE_EXTRA_PYTHONPATH:+:$LIBRELANE_EXTRA_PYTHONPATH}"
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
