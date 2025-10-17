# Custom GHDL derivation - build from source (for Linux)
{ lib, stdenv, gnat, zlib, which, pkg-config
  # Version control parameters (provided by default.nix)
  , owner ? "ghdl", repo ? "ghdl", rev, fetchSubmodules ? false, prefetchedSrc ? null
}:

stdenv.mkDerivation rec {
  pname = "ghdl";
  version = rev;

  src = if prefetchedSrc != null then prefetchedSrc else (builtins.fetchGit {
    url = "https://github.com/${owner}/${repo}.git";
    inherit rev;
  });

  nativeBuildInputs = [ pkg-config which gnat ];

  buildInputs = [ zlib ];

  # GHDL uses a custom configure script, not autotools
  configureScript = "./configure";

  configureFlags = [
    "--enable-libghdl"
    "--enable-synth"
  ];

  enableParallelBuilding = true;

  # GHDL often needs this
  hardeningDisable = [ "format" ];

  preConfigure = ''
    chmod +x configure
    export PATH=${gnat}/bin:$PATH
  '';

  meta = with lib; {
    description = "GHDL - the open-source analyzer, compiler, and simulator for VHDL (source build)";
    homepage = "https://github.com/${owner}/${repo}";
    license = licenses.gpl2Plus;
    platforms = platforms.linux;
    maintainers = [ ];
  };
}
