{
  lib,
  devshell,
  fabulous-python,
  fabulous,
  extra-packages ? [ ],
  extra-python-packages ? null,
  python-env ? null,
  extra-env ? [ ],
  editable-root ? null,
  materialize-plugin ? false,
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

  tkinterPath = "${fabulous-python.pkgs.tkinter}/${fabulous-python.sitePackages}";

  materializePlugin = lib.optionalString materialize-plugin ''
    if [ -w "$REPO_ROOT" ] && [ -f "$REPO_ROOT/build_hooks.py" ]; then
      python -c "import sys; sys.path.insert(0, '$REPO_ROOT'); import build_hooks; build_hooks.materialize_librelane_plugin()"
    fi
  '';

  prompt = ''\[\033[1;32m\][FABulous-nix:\w]\$\[\033[0m\] '';
in

devshell.mkShell {
  devshell.packages = [ pythonEnv ] ++ includedTools ++ extra-packages;

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

      if [ -z "''${REPO_ROOT:-}" ]; then
        export REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "${editable-root}")"
      fi
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
