# Docker image builder for FABulous
# This file builds a Docker image using the devShell packages from the flake
# Usage: nix-build nix/docker-image.nix
#    or: nix build -f nix/docker-image.nix

let
  # Lock to the flake's nixpkgs for consistency
  flake = builtins.getFlake (toString ./..);
  system = "x86_64-linux";
  
  # Get nixpkgs with dockerTools
  pkgs = import flake.inputs.nixpkgs { inherit system; };
  
  # Get the devShell to extract all packages from it
  devShell = flake.devShells.${system}.default;
  
  # Get the default package (FABulous virtualenv)
  fabulous-env = flake.packages.${system}.default;

  # Extract packages from devshell config (numtide/devshell stores them in passthru.config.devshell.packages)
  shellPackages = devShell.passthru.config.devshell.packages or [];
  
  # Filter out packages that aren't needed in the Docker image (like menu, interactive shells)
  filteredPackages = builtins.filter (p: 
    let name = p.name or ""; in
    name != "menu" && 
    !builtins.elem name ["fish-4.0.2" "zsh-5.9"] &&
    !(pkgs.lib.hasPrefix "fish" name) && 
    !(pkgs.lib.hasPrefix "zsh" name)
  ) shellPackages;
  
in
pkgs.dockerTools.buildLayeredImage {
  name = "fabulous";
  tag = "latest";
  
  contents = filteredPackages ++ [
    pkgs.dockerTools.caCertificates
    pkgs.dockerTools.usrBinEnv
    pkgs.dockerTools.binSh
    pkgs.coreutils
    pkgs.bash
  ];
  
  config = {
    Env = [
      "PATH=/bin"
      "PYTHONWARNINGS=ignore:Importing fasm.parse_fasm:RuntimeWarning,ignore:Falling back on slower textX parser implementation:RuntimeWarning"
    ];
    WorkingDir = "/workspace";
    Cmd = [ "${fabulous-env}/bin/FABulous" ];
  };
  
  maxLayers = 125;
}
