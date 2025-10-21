# shell.nix - For backwards compatibility with older Nix versions
# This file provides the same development environment as the flake
# Usage: nix-shell

let
  # Import the flake for backwards compatibility
  flake = builtins.getFlake (toString ./.);
  pkgs = flake.legacyPackages.${builtins.currentSystem};
in
  flake.devShells.${builtins.currentSystem}.default