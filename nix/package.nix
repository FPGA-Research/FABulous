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
  symlinkJoin,
  makeWrapper,
  zlib,
  python3,
  fabulous-python-env,
  fabulous-python-set,
  ghdl-bin,
  yosys-ghdl,
  nextpnr,
  fabulator,
  which,
  git,
  fish,
  zsh,
  gtkwave,
  nvc,
  gcc,
  gnumake,
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

  # nix-eda ships GHDL's LLVM build. Its `ghdl -e` links the simulation with the
  # shell's gcc and needs `-lz`, which the derivation keeps as a build input only.
  ghdl = symlinkJoin {
    name = "ghdl-${ghdl-bin.version}";
    paths = [ ghdl-bin ];
    nativeBuildInputs = [ makeWrapper ];
    postBuild = "wrapProgram $out/bin/ghdl --prefix LIBRARY_PATH : ${lib.getLib zlib}/lib";
  };

  # Yosys comes from librelane's `includedTools`, which already carries the ghdl
  # plugin, so FABulous and LibreLane run the same binary.
  includedTools = [
    which
    git
    fish
    zsh
    gtkwave
    nvc
    nextpnr
    fabulator
    # Build dependencies of the models Verilator generates.
    gcc
    gnumake
  ]
  # GHDL only where nix-eda builds the yosys plugin that pairs with it. Elsewhere
  # (aarch64-linux, x86_64-darwin) nixpkgs has no GHDL or no plugin, so VHDL
  # synthesis is unavailable there.
  ++ lib.optional (lib.meta.availableOn stdenv.hostPlatform yosys-ghdl) ghdl
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
