# Systematic EDA tool dependency management
# Version-controlled builds with easy hash management
{
  pkgs,
  srcs ? { },
}:

let
  # Helper function to build a tool from flake-locked sources
  buildTool =
    toolName:
    let
      pinnedSrc = srcs.${toolName}; # Assume always provided by flake
      baseArgs = {
        prefetchedSrc = pinnedSrc;
      };
    in
    if builtins.match "^[0-9a-f]{40}$" pinnedSrc.rev == null then
      builtins.error (
        "Resolved rev for " + toString toolName + " is not a commit SHA: " + toString pinnedSrc.rev
      )
    else
      pkgs.callPackage (./tools + "/${toolName}.nix") baseArgs;

in
{
  # Custom builds only for these tools
  yosys = buildTool "yosys";
  nextpnr = buildTool "nextpnr";
  fabulator = buildTool "fabulator";

  # GHDL: pre-built binaries for both platforms
  ghdl =
    let
      tarball =
        if pkgs.stdenv.isLinux then
          srcs.ghdl-linux-bin
        else if pkgs.stdenv.isDarwin then
          srcs.ghdl-darwin-bin
        else
          throw "Unsupported platform for GHDL: ${pkgs.stdenv.hostPlatform.system}";
    in
    pkgs.callPackage ./tools/ghdl-bin.nix {
      prefetchedTarball = tarball;
    };
}
