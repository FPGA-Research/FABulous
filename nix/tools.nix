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
  gcc
  gnumake
]
++ lib.optional (lib.meta.availableOn stdenv.hostPlatform yosys-ghdl) ghdl
