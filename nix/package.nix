# Consumable FABulous package: the project's console-script entrypoints
# (FABulous, fabulous) wrapped so the EDA toolchain is on PATH and the runtime
# environment is preset. This is the non-editable counterpart to the dev shell.
{
  lib,
  pkgs,
  virtualenv,
  toolchain,
}:
pkgs.runCommand "fabulous"
  {
    nativeBuildInputs = [ pkgs.makeWrapper ];
    meta = {
      description = "FABulous FPGA fabric generator (wrapped with its EDA toolchain)";
      mainProgram = "FABulous";
    };
  }
  ''
    mkdir -p $out/bin
    # librelane is wrapped too so downstream chip projects get a ready-to-run
    # front-end CLI (with the FABulous plugin discovered and the EDA tools on
    # PATH) without re-deriving the environment themselves.
    for prog in FABulous fabulous librelane; do
      # tkinter is missing from the uv-built venv's interpreter, so add it from
      # nixpkgs. librelane is intentionally NOT added: it comes from the venv
      # (pinned by uv.lock), so its version is controlled on the Python side
      # rather than forced to the flake input. librelane finds the EDA tools via
      # PATH (shutil.which), so the venv's librelane works with them as-is.
      makeWrapper ${virtualenv}/bin/$prog $out/bin/$prog \
        --prefix PATH : ${lib.makeBinPath toolchain.toolPackages} \
        --prefix PYTHONPATH : "${toolchain.tkinter-python-path}" \
        --set FAB_YOSYS_PATH ${toolchain.envVars.FAB_YOSYS_PATH} \
        --set GHDL_PREFIX ${toolchain.envVars.GHDL_PREFIX} \
        --set PYTHONWARNINGS "${toolchain.envVars.PYTHONWARNINGS}"
    done
  ''
