# Consumable FABulous package: the project's console-script entrypoints
# (FABulous, fabulous) wrapped so the EDA toolchain is on PATH and the runtime
# environment is preset. This is the non-editable counterpart to the dev shell.
#
# `passthru.includedTools` and `passthru.env` carry the toolchain and runtime
# environment, so anything built on this package reads them instead of
# re-deriving them, as with `librelane.includedTools`.
{
  lib,
  stdenv,
  runCommand,
  makeWrapper,
  python3,
  fabulous-python-env,
  fabulous-python-set,
  fabulous-tools,
}:

let
  version = fabulous-python-set.fabulous-fpga.version;

  # librelane bundles tools that are not built for every platform it evaluates
  # on, so drop the ones that do not claim this system.
  systemSupported =
    tool:
    let
      platforms = tool.meta.platforms or [ ];
    in
    platforms == [ ] || builtins.elem stdenv.hostPlatform.system platforms;

  includedTools = fabulous-tools
  ++ lib.filter systemSupported python3.pkgs.librelane.includedTools;

  # Runtime environment shared by this wrapper and every shell built from it.
  env = {
    # Silence known third-party import warnings (fasm, textX).
    PYTHONWARNINGS = "ignore:Importing fasm.parse_fasm:RuntimeWarning,ignore:Falling back on slower textX parser implementation:RuntimeWarning";
  };

in

runCommand "fabulous-${version}"
  {
    inherit version;
    pname = "fabulous";
    nativeBuildInputs = [ makeWrapper ];
    passthru = { inherit includedTools env; };
    meta = {
      description = "FABulous FPGA fabric generator (wrapped with its EDA toolchain)";
      homepage = "https://github.com/FPGA-Research/FABulous";
      license = lib.licenses.asl20;
      mainProgram = "FABulous";
    };
  }
  ''
    mkdir -p $out/bin
    # librelane is wrapped too so downstream chip projects get a ready-to-run
    # front-end CLI (with the FABulous plugin discovered and the EDA tools on
    # PATH) without re-deriving the environment themselves. It comes from the
    # Python environment, not the flake input, so uv.lock controls its version.
    #
    # `fabulous` is the lowercase alias of `FABulous`; both come from the same
    # entry point. makeWrapper fails on a missing target, so a dropped entry
    # point fails this build rather than leaving `apps.librelane` dangling.
    for prog in FABulous fabulous librelane; do
      makeWrapper ${fabulous-python-env}/bin/$prog $out/bin/$prog \
        --prefix PATH : ${lib.makeBinPath includedTools} \
        --set PYTHONWARNINGS "${env.PYTHONWARNINGS}"
    done
  ''
