# GHDL binary distribution - Linux (mcode) and macOS (llvm-jit)
{ lib, stdenv, autoPatchelfHook, zlib
  # Linux-only deps (nullable so macOS callPackage works without them)
, glibc ? null, gnat13 ? null, gcc ? null
, prefetchedTarball
}:

let
  isLinux = stdenv.isLinux;

  # The Ada runtime (libgnat-13.so) lives inside gnat's adalib directory.
  # This path is specific to the x86_64 gnat13 package in nixpkgs.
  gnatAdalib = lib.optionalString (gnat13 != null)
    "${gnat13.cc}/lib/gcc/x86_64-unknown-linux-gnu/13.4.0/adalib";
in
stdenv.mkDerivation {
  pname = "ghdl-bin";
  version = "6.0.0";

  src = prefetchedTarball;

  nativeBuildInputs = lib.optionals isLinux [ autoPatchelfHook ];

  buildInputs = [ zlib ] ++ lib.optionals isLinux [ glibc gcc.cc.lib ];

  sourceRoot = "source";

  preFixup = lib.optionalString isLinux ''
    addAutoPatchelfSearchPath ${gnatAdalib}
  '';

  installPhase = ''
    runHook preInstall

    mkdir -p $out
    cp -r ./* $out/

    if [ ! -d "$out/bin" ] || [ ! -f "$out/bin/ghdl" ]; then
      echo "Error: GHDL binary not found after install"
      exit 1
    fi

    runHook postInstall
  '';

  meta = with lib; {
    description = "GHDL - VHDL simulator (binary distribution)";
    homepage = "https://github.com/ghdl/ghdl";
    license = licenses.gpl2Plus;
    platforms = [ "x86_64-linux" "aarch64-darwin" ];
    maintainers = [ ];
  };
}
