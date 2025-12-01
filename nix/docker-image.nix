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

  # X11/Qt runtime dependencies for GUI applications (e.g., openroad -gui)
  x11Deps = with pkgs; [
    # Core X11 libraries
    xorg.libX11
    xorg.libxcb
    xorg.libXext
    xorg.libXrender
    xorg.libXi
    xorg.libXcursor
    xorg.libXrandr
    xorg.libXfixes
    xorg.libXcomposite
    xorg.libXdamage
    xorg.libXtst
    xorg.libxkbfile
    xorg.libXinerama
    xorg.libxshmfence
    xorg.xcbutilwm
    xorg.xcbutilimage
    xorg.xcbutilkeysyms
    xorg.xcbutilrenderutil
    xorg.xcbutilcursor
    
    # Additional dependencies for Qt xcb platform
    libxkbcommon
    libGL
    libGLU
    mesa
    fontconfig
    freetype
    dbus
  ];

  # Create fontconfig configuration
  fontsConf = pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; };
  
in
pkgs.dockerTools.buildLayeredImage {
  name = "fabulous";
  tag = "latest";
  
  contents = filteredPackages ++ x11Deps ++ [
    pkgs.dockerTools.caCertificates
    pkgs.dockerTools.usrBinEnv
    pkgs.dockerTools.binSh
    pkgs.dockerTools.fakeNss
    pkgs.coreutils
    pkgs.bash
    pkgs.dejavu_fonts
  ];
  
  config = {
    Env = [
      "PATH=/bin"
      "PYTHONWARNINGS=ignore:Importing fasm.parse_fasm:RuntimeWarning,ignore:Falling back on slower textX parser implementation:RuntimeWarning"
      # Fontconfig configuration for Qt applications
      "FONTCONFIG_FILE=${fontsConf}"
      # Set XDG_RUNTIME_DIR to avoid Qt warnings
      "XDG_RUNTIME_DIR=/tmp"
    ];
    WorkingDir = "/workspace";
    Cmd = [ "${fabulous-env}/bin/FABulous" ];
  };
  
  maxLayers = 125;
}
