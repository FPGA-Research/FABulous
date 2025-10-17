# GHDL binary distribution - version controlled, mcode backend where available
{ lib, stdenv, fetchurl, autoPatchelfHook, zlib
  # Version control parameters (provided by default.nix)
  , owner ? "ghdl", repo ? "ghdl", rev, originalRev ? rev
}:

let
  # Determine if this is a release version or nightly/branch based on originalRev
  isRelease = lib.hasPrefix "v" originalRev;
  
  # For version string: use originalRev if it's a tag, otherwise use commit hash
  version = if isRelease 
            then lib.removePrefix "v" originalRev
            else rev; # Use the commit hash as version for nightly
  
  # Determine the tag/branch name for URL construction
  urlTag = if isRelease then originalRev else originalRev; # "nightly", "master", etc.
  
  # Platform-specific binary information - prefer mcode backend where available
  # For nightly builds, we use the GitHub Actions artifacts which follow a different naming convention
  sources = {
    x86_64-linux = {
      # For releases: use versioned filename, for nightly: use tag-based filename
      url = if isRelease 
            then "https://github.com/${owner}/${repo}/releases/download/${originalRev}/ghdl-mcode-${version}-ubuntu24.04-x86_64.tar.gz"
            else "https://github.com/${owner}/${repo}/releases/download/${urlTag}/ghdl-mcode-ubuntu24.04-x86_64.tar.gz";
      # No hardcoded hash - will use lib.fakeSha256 and require --impure or FOD
      sha256 = null;
    };
    aarch64-linux = {
      # No official aarch64-linux binary available
      url = null;
      sha256 = null;
    };
    x86_64-darwin = {
      url = if isRelease
            then "https://github.com/${owner}/${repo}/releases/download/${originalRev}/ghdl-mcode-${version}-macos13-x86_64.tar.gz"
            else "https://github.com/${owner}/${repo}/releases/download/${urlTag}/ghdl-mcode-macos13-x86_64.tar.gz";
      sha256 = null;
    };
    aarch64-darwin = {
      # mcode backend not available for aarch64-darwin, only llvm
      # Fall back to llvm for Apple Silicon
      url = if isRelease
            then "https://github.com/${owner}/${repo}/releases/download/${originalRev}/ghdl-llvm-${version}-macos15-aarch64.tar.gz"
            else "https://github.com/${owner}/${repo}/releases/download/${urlTag}/ghdl-llvm-macos15-aarch64.tar.gz";
      sha256 = null;
    };
  };

  platformInfo = sources.${stdenv.hostPlatform.system} or (throw "Unsupported platform: ${stdenv.hostPlatform.system}");

in
assert platformInfo.url != null || abort "No pre-built GHDL binary available for ${stdenv.hostPlatform.system} with version ${version}";

stdenv.mkDerivation rec {
  pname = "ghdl-bin";
  inherit version;

  src = fetchurl {
    inherit (platformInfo) url;
    # Use lib.fakeSha256 for FOD (Fixed Output Derivation)
    # Nix will automatically determine the correct hash
    sha256 = lib.fakeSha256;
  };

  nativeBuildInputs = lib.optionals stdenv.isLinux [ autoPatchelfHook ];

  buildInputs = [ zlib ];

  # The tarball contains a directory structure like: ghdl-{backend}-X.X.X-{platform}-{arch}/
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
    description = "GHDL - VHDL simulator (binary distribution, mcode backend where available)";
    homepage = "https://github.com/${owner}/${repo}";
    license = licenses.gpl2Plus;
    platforms = [ "x86_64-linux" "x86_64-darwin" "aarch64-darwin" ];
    maintainers = [ ];
  };
}