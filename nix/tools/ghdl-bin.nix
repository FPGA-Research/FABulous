# GHDL binary distribution - for macOS only
{ lib, stdenv, fetchurl, zlib
  # Version control parameters (provided by default.nix)
  , owner ? "ghdl", repo ? "ghdl", prefetchedTarball
}:

let
  # Hardcoded tag for binary logic (matches flake input)
  originalRev = "nightly";
  
  # Determine if this is a release version or nightly/branch based on originalRev
  isRelease = lib.hasPrefix "v" originalRev;
  
  # For version string
  version = "unstable";
  
  # Platform-specific binary information - Apple Silicon only (llvm-jit backend)
  sources = {
    aarch64-darwin = {
      url = if isRelease
            then "https://github.com/${owner}/${repo}/releases/download/${originalRev}/ghdl-llvm-jit-${lib.removePrefix "v" originalRev}-macos15-aarch64.tar.gz"
            else "https://github.com/${owner}/${repo}/releases/download/nightly/ghdl-llvm-jit-6.0.0-dev-macos15-aarch64.tar.gz";
      sha256 = null;
    };
  };

  platformInfo = sources.${stdenv.hostPlatform.system} or (throw "Unsupported platform for binary build: ${stdenv.hostPlatform.system}");

in
stdenv.mkDerivation rec {
  pname = "ghdl-bin";
  inherit version;

  src = prefetchedTarball;

  buildInputs = [ zlib ];

  # When using prefetchedTarball (flake input), Nix extracts to 'source'
  sourceRoot = "source";

  installPhase = ''
    runHook preInstall

    mkdir -p $out
    
    cp -r ./* $out/

    # Verify installation
    if [ ! -d "$out/bin" ] || [ ! -f "$out/bin/ghdl" ]; then
      echo "Error: GHDL installation failed"
      exit 1
    fi

    runHook postInstall
  '';

  meta = with lib; {
    description = "GHDL - VHDL simulator (binary distribution for macOS Apple Silicon)";
    homepage = "https://github.com/${owner}/${repo}";
    license = licenses.gpl2Plus;
    platforms = [ "aarch64-darwin" ];
    maintainers = [ ];
  };
}
