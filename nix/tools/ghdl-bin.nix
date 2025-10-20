# GHDL binary distribution - for macOS only
{ lib, stdenv, fetchurl, zlib
  # Version control parameters (provided by default.nix)
  , owner ? "ghdl", repo ? "ghdl", rev, originalRev ? rev
  # Optional pre-fetched tarball (e.g., from flake inputs locked in flake.lock)
  , prefetchedTarball ? null
}:

let
  # Determine if this is a release version or nightly/branch based on originalRev
  isRelease = lib.hasPrefix "v" originalRev;
  
  # For version string: use originalRev if it's a tag, otherwise use commit hash
  version = if isRelease 
            then lib.removePrefix "v" originalRev
            else rev;
  
  # Platform-specific binary information - Apple Silicon only (llvm-jit backend)
  sources = {
    aarch64-darwin = {
      url = if isRelease
            then "https://github.com/${owner}/${repo}/releases/download/${originalRev}/ghdl-llvm-jit-${version}-macos15-aarch64.tar.gz"
            else "https://github.com/${owner}/${repo}/releases/download/nightly/ghdl-llvm-jit-6.0.0-dev-macos15-aarch64.tar.gz";
      sha256 = null;
    };
  };

  platformInfo = sources.${stdenv.hostPlatform.system} or (throw "Unsupported platform for binary build: ${stdenv.hostPlatform.system}");

in
assert platformInfo.url != null || abort "No pre-built GHDL binary available for ${stdenv.hostPlatform.system}";

stdenv.mkDerivation rec {
  pname = "ghdl-bin";
  inherit version;

  src = if prefetchedTarball != null then prefetchedTarball else fetchurl {
    inherit (platformInfo) url;
    sha256 = lib.fakeSha256;
  };

  buildInputs = [ zlib ];

  # When using prefetchedTarball (flake input), Nix extracts to 'source'
  # When using fetchurl, it extracts to the directory inside the tarball
  sourceRoot = if prefetchedTarball != null then "source" else ".";

  installPhase = ''
    runHook preInstall

    mkdir -p $out
    
    # With sourceRoot set correctly, we can copy directly
    # For flake input: sourceRoot="source" and we're already in it
    # For fetchurl: sourceRoot="." and we need to find ghdl-* dir
    ${if prefetchedTarball != null then ''
      cp -r ./* $out/
    '' else ''
      GHDL_DIR=$(find . -maxdepth 1 -type d -name "ghdl-*" -print -quit)
      if [ -z "$GHDL_DIR" ]; then
        echo "Error: Could not find ghdl-* directory"
        ls -la
        exit 1
      fi
      cp -r "$GHDL_DIR"/* $out/
    ''}

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
