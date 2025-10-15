# Yosys - Synthesis tool
{ lib
, stdenv
, pkg-config
, bison
, flex
, tcl
, readline
, libffi
, python3
, zlib
, git  # Needed for version detection
, owner
, repo
, rev
, fetchSubmodules ? true
}:

stdenv.mkDerivation rec {
  pname = "yosys";
  version = if (lib.hasPrefix "v" rev) then lib.removePrefix "v" rev else "dev-${lib.substring 0 7 rev}";

  src = builtins.fetchGit {
    url = "https://github.com/${owner}/${repo}.git";
    rev = rev;
  };

  nativeBuildInputs = [
    pkg-config
    bison
    flex
    git  # For version detection
  ];

  buildInputs = [
    tcl
    readline
    libffi
    python3
    zlib
  ];

  makeFlags = [
    "PREFIX=${placeholder "out"}"
    "ENABLE_TCL=1"
    "ENABLE_ABC=1"
    "ENABLE_GLOB=1"
    "ENABLE_PLUGINS=1"
    "ENABLE_READLINE=1"
    "ENABLE_COVER=1"
  ];

  # Handle ABC submodule and version detection
  preBuild = ''
    # Export version info for build
    export YOSYS_VER="${version}"

    # Handle ABC if available
    if [ -d abc ]; then
      export ABCREV=$(cat abc/abc_exe_start.txt 2>/dev/null || echo "unknown")
    fi
  '';

  enableParallelBuilding = true;

  # Install additional files
  postInstall = ''
    # Install techmap files and other data
    mkdir -p $out/share/yosys
    cp -r techlibs $out/share/yosys/ || true
    cp -r passes $out/share/yosys/ || true
  '';

  meta = with lib; {
    description = "Yosys Open SYnthesis Suite";
    longDescription = ''
      Yosys is a framework for Verilog RTL synthesis. It currently has
      extensive Verilog-2005 support and provides a basic set of
      synthesis algorithms for various application domains.
    '';
    homepage = "https://yosyshq.net/yosys/";
    license = licenses.isc;
    platforms = platforms.linux ++ platforms.darwin;
    maintainers = with maintainers; [ ];
  };
}