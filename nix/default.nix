# Systematic EDA tool dependency management
# Version-controlled builds with easy hash management
{ pkgs, srcs ? { } }:

let
  # Helper function to build a tool from flake-locked sources
  buildTool = toolName:
    let
      pinnedSrc = srcs.${toolName};  # Assume always provided by flake
      baseArgs = {
        prefetchedSrc = pinnedSrc;
      };
    in
      if builtins.match "^[0-9a-f]{40}$" pinnedSrc.rev == null then
        builtins.error ("Resolved rev for " + toString toolName + " is not a commit SHA: " + toString pinnedSrc.rev)
      else
        pkgs.callPackage (./tools + "/${toolName}.nix") baseArgs;

in
{
  # Custom builds only for these tools
  nextpnr = buildTool "nextpnr";
  
  # GHDL: Build from source on Linux, use pre-built binaries on macOS
  ghdl = let
    # Always use the commit hash from flake lock for reproducibility
    flakeLocked = srcs.ghdl;
    commit = flakeLocked.rev;
    
    # Choose derivation based on platform
    isLinux = pkgs.stdenv.isLinux;
    ghdlDerivation = if isLinux then
      ./tools/ghdl-src.nix
    else if pkgs.stdenv.isDarwin then
      ./tools/ghdl-bin.nix
    else
      throw "Unsupported platform for GHDL";
    
    # Platform-specific arguments
    args = if isLinux then {
      # Only pass prefetchedSrc if available
      prefetchedSrc = flakeLocked;
    } else {
      prefetchedTarball = srcs.ghdl-darwin-bin or null;
    };
    
  in pkgs.callPackage ghdlDerivation args;
}