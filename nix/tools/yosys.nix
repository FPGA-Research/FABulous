# Yosys - RTL synthesis tool (custom build as fab-yosys)
{
  lib,
  stdenv,
  bison,
  flex,
  pkg-config,
  libffi,
  readline,
  tcl,
  zlib,
  python3,
  prefetchedSrc,
}:

let
  shortRev = builtins.substring 0 9 prefetchedSrc.rev;
in

stdenv.mkDerivation {
  pname = "fab-yosys";
  version = "unstable";

  src = prefetchedSrc;

  nativeBuildInputs = [
    bison
    flex
    pkg-config
  ];

  buildInputs = [
    libffi
    readline
    tcl
    zlib
    python3
  ];

  postPatch = ''
    # Patch out git operations for version detection
    substituteInPlace Makefile \
      --replace-fail 'GIT_COMMIT_COUNT := $(or $(shell git rev-list --count v$(YOSYS_VER)..HEAD 2>/dev/null),0)' \
                     'GIT_COMMIT_COUNT := 0' \
      --replace-fail 'GIT_REV := $(shell GIT_DIR=$(YOSYS_SRC)/.git git rev-parse --short=9 HEAD || echo UNKNOWN)' \
                     'GIT_REV := ${shortRev}'

    # Stub the git-abc-submodule-hash so abc builds without git
    echo "none" > .git-abc-submodule-hash

    # Replace the check-git-abc target with a no-op
    substituteInPlace Makefile \
      --replace-fail '| check-git-abc' ""

    # Fix ABC build directory: PROGRAM_PREFIX causes it to look for fab-abc/ instead of abc/
    substituteInPlace Makefile \
      --replace-fail '$(MAKE) -C $(PROGRAM_PREFIX)abc' '$(MAKE) -C abc'

    patchShebangs .
  '';

  preBuild = ''
    make ${if stdenv.cc.isClang then "config-clang" else "config-gcc"}
  '';

  makeFlags = [
    "PREFIX=${placeholder "out"}"
    "PROGRAM_PREFIX=fab-"
  ];

  enableParallelBuilding = true;

  meta = with lib; {
    description = "Yosys Open SYnthesis Suite (FABulous build)";
    longDescription = ''
      Yosys is a framework for RTL synthesis tools. This is a custom build
      for FABulous, installed as fab-yosys to avoid conflicts with system yosys.
    '';
    homepage = "https://github.com/YosysHQ/yosys";
    license = licenses.isc;
    platforms = platforms.linux ++ platforms.darwin;
  };
}
