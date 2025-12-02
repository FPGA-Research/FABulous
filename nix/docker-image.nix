# Docker image builder for FABulous
# This file builds Docker images using the devShell packages from the flake
#
# Usage:
#   nix-build nix/docker-image.nix                    # Builds dev image (editable install)
#   nix-build nix/docker-image.nix -A dev             # Builds dev image (editable install)
#   nix-build nix/docker-image.nix -A release         # Builds release image (non-editable)

let
  # Lock to the flake's nixpkgs for consistency
  flake = builtins.getFlake (toString ./..);
  system = "x86_64-linux";
  
  # Get nixpkgs with dockerTools
  pkgs = import flake.inputs.nixpkgs { inherit system; };
  
  # Get the devShell to extract all packages from it (includes editable FABulous + EDA tools)
  devShell = flake.devShells.${system}.default;
  
  # Get the default package (non-editable FABulous virtualenv)
  fabulous-env = flake.packages.${system}.default;

  # Extract packages from devshell config (numtide/devshell stores them in passthru.config.devshell.packages)
  shellPackages = devShell.passthru.config.devshell.packages or [];
  
  # Filter out packages that aren't needed in the Docker image (like menu, interactive shells)
  # Also filter out the editable FABulous-env for release builds
  filteredPackages = builtins.filter (p: 
    let name = p.name or ""; in
    name != "menu" && 
    !builtins.elem name ["fish-4.0.2" "zsh-5.9"] &&
    !(pkgs.lib.hasPrefix "fish" name) && 
    !(pkgs.lib.hasPrefix "zsh" name)
  ) shellPackages;

  # For release: filter out the editable FABulous-env, we'll add non-editable one
  releasePackages = builtins.filter (p: 
    let name = p.name or ""; in
    !(pkgs.lib.hasPrefix "FABulous-env" name)
  ) filteredPackages;

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

  # Common base packages
  basePackages = x11Deps ++ [
    pkgs.dockerTools.caCertificates
    pkgs.dockerTools.usrBinEnv
    pkgs.dockerTools.binSh
    pkgs.dockerTools.fakeNss
    pkgs.coreutils
    pkgs.bash
    pkgs.dejavu_fonts
    # Required for VS Code Dev Containers to work properly
    pkgs.gnutar       # for extracting VS Code Server
    pkgs.gzip         # for decompressing archives
    pkgs.gnused       # for environment setup
    pkgs.gnugrep      # for user lookup and config parsing
    pkgs.findutils    # for find command
    pkgs.procps       # for ps command (process listing)
    pkgs.gawk         # for awk command
    # Required for VS Code Server runtime (libraries linked by node binary)
    pkgs.glibc              # provides libc.so
    pkgs.stdenv.cc.cc.lib   # provides libstdc++.so (GLIBCXX)
    # Nice to have utilities for development
    pkgs.curl         # for downloading files
    pkgs.wget         # alternative downloader
    pkgs.openssh      # for SSH connections
    pkgs.less         # pager for viewing files
    pkgs.gnupatch     # for applying patches
  ];

  # Build LD_LIBRARY_PATH for VS Code Server to find libraries
  libPath = pkgs.lib.makeLibraryPath [
    pkgs.glibc
    pkgs.stdenv.cc.cc.lib
  ];

  # Common environment variables
  baseEnv = [
    "PATH=/bin"
    "PYTHONWARNINGS=ignore:Importing fasm.parse_fasm:RuntimeWarning,ignore:Falling back on slower textX parser implementation:RuntimeWarning"
    "FONTCONFIG_FILE=${fontsConf}"
    "XDG_RUNTIME_DIR=/tmp"
    "LD_LIBRARY_PATH=${libPath}"
  ];

  # Create FHS compatibility layer for VS Code Dev Containers
  # - Dynamic linker symlink is required for VS Code Server binaries to run
  # - os-release identifies as NixOS so VS Code skips glibc version checks
  fhsLibs = pkgs.runCommand "fhs-libs" {} ''
    mkdir -p $out/lib64 $out/etc
    # Create the dynamic linker symlink - required for VS Code Server binaries to run
    ln -s ${pkgs.glibc}/lib/ld-linux-x86-64.so.2 $out/lib64/ld-linux-x86-64.so.2
    # Create os-release identifying as NixOS so VS Code skips glibc checks
    cat > $out/etc/os-release << EOF
ID=nixos
NAME="NixOS"
VERSION_ID="24.11"
PRETTY_NAME="NixOS 24.11"
EOF
  '';

  # Dev image: editable install (for FABulous development)
  devImage = pkgs.dockerTools.buildLayeredImage {
    name = "fabulous";
    tag = "dev";
    
    contents = filteredPackages ++ basePackages ++ [ fhsLibs ];
    
    config = {
      Env = baseEnv ++ [
        # Set REPO_ROOT for editable install - mount FABulous repo at /workspace
        "REPO_ROOT=/workspace"
      ];
      WorkingDir = "/workspace";
      Cmd = [ "/bin/bash" ];
    };
    
    maxLayers = 125;
  };

  # Release image: non-editable install (for end users)
  releaseImage = pkgs.dockerTools.buildLayeredImage {
    name = "fabulous";
    tag = "latest";
    
    contents = releasePackages ++ [ fabulous-env ] ++ basePackages ++ [ fhsLibs ];
    
    config = {
      Env = baseEnv;
      WorkingDir = "/workspace";
      Cmd = [ "/bin/bash" ];
    };
    
    maxLayers = 125;
  };

in
{
  # Default to dev image for backward compatibility with current CI
  default = devImage;
  dev = devImage;
  release = releaseImage;
}
