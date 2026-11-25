# The tools FABulous adds to librelane's `includedTools`. Yosys is not here: it
# comes from librelane, whose build already carries the ghdl plugin, so FABulous
# and LibreLane run the same binary.
{
  lib,
  stdenv,
  symlinkJoin,
  makeWrapper,
  zlib,
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
  # nix-eda ships GHDL's LLVM build. Its `ghdl -e` links the simulation with the
  # shell's gcc and needs `-lz`, which the derivation keeps as a build input only.
  ghdl = symlinkJoin {
    name = "ghdl-${ghdl-bin.version}";
    paths = [ ghdl-bin ];
    nativeBuildInputs = [ makeWrapper ];
    postBuild = "wrapProgram $out/bin/ghdl --prefix LIBRARY_PATH : ${lib.getLib zlib}/lib";
  };
in
[
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
