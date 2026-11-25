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

  systemSupported =
    tool:
    let
      platforms = tool.meta.platforms or [ ];
    in
    platforms == [ ] || builtins.elem stdenv.hostPlatform.system platforms;

  includedTools = fabulous-tools ++ lib.filter systemSupported python3.pkgs.librelane.includedTools;

  env = {
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
    for prog in FABulous fabulous librelane; do
      makeWrapper ${fabulous-python-env}/bin/$prog $out/bin/$prog \
        --prefix PATH : ${lib.makeBinPath includedTools} \
        --set PYTHONWARNINGS "${env.PYTHONWARNINGS}"
    done
  ''
