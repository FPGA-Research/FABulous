# Consumer shell for downstream projects (chip / fabric builds) that depend on
# FABulous. The venv is the hermetic uv.lock-built environment (FABulous +
# librelane + the GDS plugin), so FABulous's own Python world is pinned by
# uv.lock and only changes via fork + PR upstream.
#
# Two extension surfaces, mirroring librelane-shell.override:
#   - extraPackages       : non-Python tools the project brings (simulators,
#                           waveform viewers, make). A list, or `pkgs: [ ... ]`.
#   - extraPythonPackages : the project's OWN Python tooling (cocotb, ...),
#                           selected from nixpkgs' python set as `ps: [ ... ]`.
#
# CAVEAT on extraPythonPackages: these are resolved by nixpkgs, not uv.lock, and
# layered onto the venv via PYTHONPATH. The venv's uv.lock-pinned site-packages
# is placed FIRST, so its versions win for any shared dependency; but a package
# that needs a version the venv does not provide can still clash. Keep this set
# small (verification tooling) and move anything FABulous itself needs into
# uv.lock instead.
{
  pkgs,
  python,
  toolchain,
  virtualenv,
}:
{
  extraPackages ? [ ],
  extraPythonPackages ? (ps: [ ]),
}:
let
  inherit (toolchain) tkinter-python-path envVars toolPackages;
  resolvedTools = if builtins.isFunction extraPackages then extraPackages pkgs else extraPackages;
  # The consumer's nixpkgs Python packages, bundled into one env (built with the
  # SAME python as the venv, so ABI-compatible) whose site-packages is appended
  # to PYTHONPATH after the venv's.
  extraPythonEnv = python.withPackages extraPythonPackages;
  extraPythonSite = "${extraPythonEnv}/${python.sitePackages}";
in
pkgs.mkShell {
  packages = [ virtualenv ] ++ toolPackages ++ resolvedTools;

  FAB_YOSYS_PATH = envVars.FAB_YOSYS_PATH;
  GHDL_PREFIX = envVars.GHDL_PREFIX;
  PYTHONWARNINGS = envVars.PYTHONWARNINGS;

  shellHook = ''
    . ${virtualenv}/bin/activate
    VENV_SITE=$(python -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)
    # venv (uv.lock) site FIRST so its versions win for shared deps; tkinter and
    # the consumer's nixpkgs Python extras follow.
    export PYTHONPATH="$VENV_SITE:${tkinter-python-path}:${extraPythonSite}''${PYTHONPATH:+:$PYTHONPATH}"
  '';
}
