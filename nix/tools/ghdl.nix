# Custom GHDL derivation with mcode backend from master branch
{ lib, stdenv, gnat ? null, llvm ? null, zlib, which, pkg-config, darwin ? null
  # Version control parameters (provided by default.nix)
  , owner ? "ghdl", repo ? "ghdl", rev, fetchSubmodules ? false, prefetchedSrc ? null
}:

stdenv.mkDerivation rec {
  pname = "ghdl-master";
  version = if rev == "master" then "5.0-dev" else rev;

  src = if prefetchedSrc != null then prefetchedSrc else (builtins.fetchGit {
    url = "https://github.com/${owner}/${repo}.git";
    inherit rev;
  });

  # Choose native build inputs depending on platform/backend availability
  nativeBuildInputs = (
    if stdenv.isDarwin then
      [ pkg-config which ] ++ lib.optionals (llvm != null) [ llvm ]
    else
      [ pkg-config which ] ++ lib.optionals (gnat != null) [ gnat ]
  ) ++ lib.optionals stdenv.isDarwin [ darwin.cctools ];

  buildInputs = [
    zlib
  ];

  # GHDL uses a custom configure script, not autotools
  configureScript = "./configure";

  configureFlags = [
    "--enable-libghdl"
    "--enable-synth"
  ];

  enableParallelBuilding = true;

  # GHDL often needs this
  hardeningDisable = [ "format" ];

  # Set up environment variables for the selected backend
  preConfigure = ''
    chmod +x configure
  '' + lib.concatStringsSep "\n" (lib.optionals (stdenv.isDarwin && (llvm != null)) [ ''
    # Use LLVM/clang on Darwin
    export CC=${llvm}/bin/clang
    export CXX=${llvm}/bin/clang++
  '' ]) + lib.concatStringsSep "\n" (lib.optionals (!stdenv.isDarwin && (gnat != null)) [ ''
    # Use GNAT on non-Darwin
    export PATH=${gnat}/bin:$PATH
  '' ]);

  meta = with lib; {
    description = "GHDL - the open-source analyzer, compiler, and simulator for VHDL with mcode backend (master branch)";
    homepage = "https://github.com/ghdl/ghdl";
    license = licenses.gpl2Plus;
    platforms = platforms.linux ++ platforms.darwin;
    maintainers = with maintainers; [ ];
  };
}