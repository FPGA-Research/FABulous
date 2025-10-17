# GHDL binary distribution - for macOS only
{ lib, stdenv, fetchurl, zlib
  # Version control parameters (provided by default.nix)
  , owner ? "ghdl", repo ? "ghdl", rev, originalRev ? rev
}:

let
  # Determine if this is a release version or nightly/branch based on originalRev
  isRelease = lib.hasPrefix "v" originalRev;
  
  # For version string: use originalRev if it's a tag, otherwise use commit hash
  version = if isRelease 
            then lib.removePrefix "v" originalRev
            else rev;
  
  # Platform-specific binary information - prefer mcode backend where available
  sources = {
    x86_64-darwin = {
      url = if isRelease
            then "https://github.com/${owner}/${repo}/releases/download/${originalRev}/ghdl-mcode-${version}-macos13-x86_64.tar.gz"
            else "https://github.com/${owner}/${repo}/releases/download/nightly/ghdl-mcode-macos13-x86_64.tar.gz";
      sha256 = null;
    };
    aarch64-darwin = {
      # mcode backend not available for aarch64-darwin, use llvm-jit instead
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

  src = fetchurl {
    inherit (platformInfo) url;
    # Use lib.fakeSha256 for FOD (Fixed Output Derivation)
    sha256 = lib.fakeSha256;
  };

  buildInputs = [ zlib ];

  sourceRoot = ".";

  installPhase = ''
    runHook preInstall

    # Find the extracted directory (it will match ghdl-*)
    GHDL_DIR=$(find . -maxdepth 1 -type d -name "ghdl-*" | head -n1)
    
    if [ -z "$GHDL_DIR" ]; then
      echo "Error: Could not find GHDL directory in extracted archive"
      exit 1
    fi

    # Copy everything to output
    mkdir -p $out
    cp -r "$GHDL_DIR"/* $out/

    # Ensure bin directory exists
    if [ ! -d "$out/bin" ]; then
      echo "Error: No bin directory found in GHDL distribution"
      exit 1
    fi

    runHook postInstall
  '';

  meta = with lib; {
    description = "GHDL - VHDL simulator (binary distribution for macOS)";
    homepage = "https://github.com/${owner}/${repo}";
    license = licenses.gpl2Plus;
    platforms = [ "x86_64-darwin" "aarch64-darwin" ];
    maintainers = [ ];
  };
}
