# Systematic EDA tool dependency management
# Version-controlled builds with easy hash management
{ pkgs, srcs ? { } }:

let
  # Import version configurations
  versions = import ./versions.nix;

  # Helper function to build a tool from configuration.
  # NOTE: For pure, reproducible builds, prefer pinning `rev` to a commit SHA
  # in versions.nix. Tags may work via builtins.fetchGit in the tool derivation,
  # but are less reproducible.
  # Resolve rev from versions.nix to a commit SHA before calling the tool derivation.
  # In impure dev shells, resolve non-SHA revs by trying a tag ref first, then a branch ref.
  buildTool = toolName:
    let
      config = versions.${toolName};
      hasRev = config ? rev;
      revVal = if hasRev then config.rev else "";
      isCommit = hasRev && builtins.match "^[0-9a-f]{40}$" revVal != null;
      pinnedSrc = srcs.${toolName} or null;
      commit = if !hasRev then
        builtins.error ("versions.nix must provide a 'rev' (commit or tag) for tool: " + toString toolName)
      else if isCommit then
        revVal
      else
        # For a tag/branch: prefer flake-locked srcs when provided; otherwise try to resolve tag/branch (impure)
        if pinnedSrc != null then pinnedSrc.rev else (
          let
            url = "https://github.com/${config.owner}/${config.repo}.git";
            tryRef = ref: builtins.tryEval ((builtins.fetchGit { inherit url ref; }).rev);
            tagAttempt = tryRef ("refs/tags/" + revVal);
            branchAttempt = tryRef ("refs/heads/" + revVal);
          in if tagAttempt.success then tagAttempt.value
             else if branchAttempt.success then branchAttempt.value
             else builtins.error ("Could not resolve rev '" + revVal + "' for " + toString toolName + " as tag or branch")
        );
      # Build the base arguments for the tool
      baseArgs = {
        inherit (config) owner repo;
        rev = commit;
        fetchSubmodules = config.fetchSubmodules or false;
      } // (if (!isCommit) && (pinnedSrc != null) then { prefetchedSrc = pinnedSrc; } else { });
    in
      if builtins.match "^[0-9a-f]{40}$" commit == null then
        builtins.error ("Resolved rev for " + toString toolName + " is not a commit SHA: " + toString commit)
      else
        pkgs.callPackage (./tools + "/${toolName}.nix") baseArgs;

in
{
  # Custom builds only for these tools
  nextpnr = buildTool "nextpnr";
  
  # GHDL: Build from source on Linux, use pre-built binaries on macOS
  ghdl = let
    config = versions.ghdl;
    # Always use the commit hash from flake lock for reproducibility
    flakeLocked = srcs.ghdl or null;
    commit = if flakeLocked != null then flakeLocked.rev else config.rev;
    
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
      inherit (config) owner repo;
      rev = commit;
      # Only pass prefetchedSrc if available
    } // (if flakeLocked != null then { prefetchedSrc = flakeLocked; } else {})
    else {
      inherit (config) owner repo;
      rev = commit;
      originalRev = config.rev;
      prefetchedTarball = srcs.ghdl-darwin-bin or null;
    };
    
  in pkgs.callPackage ghdlDerivation args;

  # Export the versions for inspection
  edaVersions = versions;
}