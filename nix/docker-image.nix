# Docker image builder for FABulous
# Based on https://github.com/nix-community/docker-nixpkgs/blob/main/images/devcontainer/default.nix
#
# This creates a dev container compatible with VS Code Remote Containers
# All dependencies are managed through Nix for reproducibility

let
  # Lock to the flake's nixpkgs for consistency
  flake = builtins.getFlake (toString ./..);
  system = "x86_64-linux";
  pkgs = import flake.inputs.nixpkgs { inherit system; };

  # Get the devShell to extract all packages from it (includes editable FABulous + EDA tools)
  devShell = flake.devShells.${system}.default;

  # Get the default package (non-editable FABulous virtualenv)
  fabulous-env = flake.packages.${system}.default;

  # Extract packages from devshell config
  shellPackages = devShell.passthru.config.devshell.packages or[];

  # Filter out packages that aren't needed in the Docker image
  filteredPackages = builtins.filter (p:
    let name = p.name or ""; in
    name != "menu" &&
    !builtins.elem name ["fish-4.0.2" "zsh-5.9"] &&
    !(pkgs.lib.hasPrefix "fish" name) &&
    !(pkgs.lib.hasPrefix "zsh" name) &&
    !(pkgs.lib.hasPrefix "git-" name)  # Exclude git, we'll use gitMinimal
  ) shellPackages;

  # For release: filter out the editable FABulous-env
  releasePackages = builtins.filter (p:
    let name = p.name or ""; in
    !(pkgs.lib.hasPrefix "FABulous-env" name)
  ) filteredPackages;

  # Create fontconfig configuration
  fontsConf = pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; };

  # Core utilities and tools needed by both dev and release (from docker-nixpkgs)
  basePackages = [
    # Core utils
    pkgs.coreutils
    pkgs.procps
    pkgs.gnugrep
    pkgs.gnused
    pkgs.less

    # Bash shell
    pkgs.bashInteractive

    # Nix itself
    pkgs.nix

    # Runtime dependencies of nix
    (pkgs.cacert // {
      outputs = builtins.filter (x: x != "hashed") pkgs.cacert.outputs;
    })
    pkgs.gitMinimal
    pkgs.gnutar
    pkgs.gzip
    pkgs.xz

    # User management
    pkgs.shadow

    # VS Code extension requirements
    (pkgs.gcc-unwrapped // {
      outputs = builtins.filter (x: x != "libgcc") pkgs.gcc-unwrapped.outputs;
    })
    pkgs.iproute2

    # Additional dependencies for VS Code compatibility
    pkgs.glibc
    pkgs.glibc.bin  # Provides ldconfig
    pkgs.stdenv.cc.cc.lib  # Provides libstdc++
    pkgs.findutils
  ];

  # X11 libraries for GUI support
  x11Packages = [
    pkgs.xorg.libX11
    pkgs.xorg.libxcb
    pkgs.xorg.libXext
    pkgs.xorg.libXrender
    pkgs.xorg.libXi
    pkgs.xorg.libXcursor
    pkgs.xorg.libXrandr
    pkgs.xorg.libXfixes
    pkgs.xorg.libXcomposite
    pkgs.xorg.libXdamage
    pkgs.xorg.libXtst
    pkgs.xorg.libxkbfile
    pkgs.xorg.libXinerama
    pkgs.xorg.libxshmfence
    pkgs.xorg.xcbutilwm
    pkgs.xorg.xcbutilimage
    pkgs.xorg.xcbutilkeysyms
    pkgs.xorg.xcbutilrenderutil
    pkgs.xorg.xcbutilcursor
  ];

  # Qt and graphics dependencies for GUI applications
  qtGraphicsPackages = [
    pkgs.libxkbcommon
    pkgs.libGL
    pkgs.libGLU
    pkgs.mesa
    pkgs.fontconfig
    pkgs.freetype
    pkgs.dbus
    # Explicitly include qtbase to ensure platform plugins are available
    pkgs.qt5.qtbase.bin
  ];

  # Helper to create a user environment (like docker-nixpkgs mkUserEnvironment)
  mkUserEnvironment = { derivations }: pkgs.buildEnv {
    name = "user-environment";
    paths = derivations;
    pathsToLink = [ "/bin" "/lib" "/share" "/etc" ];
    extraOutputsToInstall = [ "out" "bin" "lib" ];
  };

  # Create extraCommands script for Docker image (shared between dev and release)
  mkExtraCommands = profile: ''
    # Create the Nix DB
    export NIX_REMOTE=local?root=$PWD
    export USER=nobody
    ${pkgs.nix}/bin/nix-store --load-db < ${pkgs.closureInfo { rootPaths = [ profile ]; }}/registration

    # Set the user profile
    ${profile}/bin/nix-env --profile nix/var/nix/profiles/default --set ${profile}

    # Minimal FHS structure
    mkdir -p bin usr/bin
    ln -s /nix/var/nix/profiles/default/bin/sh bin/sh
    ln -s /nix/var/nix/profiles/default/bin/env usr/bin/env
    ln -s /nix/var/nix/profiles/default/bin/bash bin/bash

    # Setup shadow, bashrc
    mkdir home
    mkdir -p etc
    chmod +w etc

    # Setup iana-etc for haskell binaries
    ln -s /nix/var/nix/profiles/default/etc/protocols etc/protocols
    ln -s /nix/var/nix/profiles/default/etc/services etc/services

    # Make sure /tmp exists
    mkdir -m 0777 tmp

    # Allow ubuntu ELF binaries to run. VSCode copies its own.
    mkdir -p lib64
    ln -s ${pkgs.glibc}/lib64/ld-linux-x86-64.so.2 lib64/ld-linux-x86-64.so.2

    # VSCode assumes that /sbin/ip exists
    mkdir sbin
    ln -s /nix/var/nix/profiles/default/bin/ip sbin/ip

    # Create workspace directory
    mkdir -p workspace
    chmod 755 workspace

    # Create os-release
    cat > etc/os-release << 'EOF'
NAME="NixOS"
ID=nixos
VERSION="24.05"
PRETTY_NAME="NixOS 24.05 (Uakari)"
EOF

    # Setup minimal shadow files
    echo "root:x:0:0::/root:/bin/bash" > etc/passwd
    echo "root:x:0:" > etc/group
    echo "root:!:1::::::" > etc/shadow
  '';

  # Create Docker config with optional dev-specific env vars
  mkDockerConfig = { isDev ? false }: {
    Cmd = [ "/nix/var/nix/profiles/default/bin/bash" ];
    Env = [
      "PATH=/nix/var/nix/profiles/default/bin"
      "LD_LIBRARY_PATH=/nix/var/nix/profiles/default/lib"
      "GIT_SSL_CAINFO=/nix/var/nix/profiles/default/etc/ssl/certs/ca-bundle.crt"
      "SSL_CERT_FILE=/nix/var/nix/profiles/default/etc/ssl/certs/ca-bundle.crt"
      "PAGER=less"
      "FONTCONFIG_FILE=${fontsConf}"
      "XDG_RUNTIME_DIR=/tmp"
      "PYTHONWARNINGS=ignore:Importing fasm.parse_fasm:RuntimeWarning,ignore:Falling back on slower textX parser implementation:RuntimeWarning"
    ] ++ pkgs.lib.optionals isDev [
      # Dev-specific: Set REPO_ROOT for editable install
      "REPO_ROOT=/workspace"
    ];
    WorkingDir = "/workspace";
    Labels = {
      "org.label-schema.vcs-url" = "https://github.com/FPGA-Research-Manchester/FABulous";
    };
  };

  # Dev profile with GUI support and editable FABulous
  devProfile = mkUserEnvironment {
    derivations = filteredPackages ++ basePackages ++ x11Packages ++ qtGraphicsPackages;
  };

  # Release profile with GUI support and non-editable FABulous
  releaseProfile = mkUserEnvironment {
    derivations = releasePackages ++ [fabulous-env] ++ basePackages ++ x11Packages ++ qtGraphicsPackages;
  };

  # Build the dev image (following docker-nixpkgs pattern with GUI support)
  devImage = pkgs.dockerTools.buildImage {
    name = "fabulous";
    tag = "dev";
    contents = [ ];
    extraCommands = mkExtraCommands devProfile;
    config = mkDockerConfig { isDev = true; };
  };

  # Build the release image (non-editable FABulous with GUI support)
  releaseImage = pkgs.dockerTools.buildImage {
    name = "fabulous";
    tag = "latest";
    contents = [ ];
    extraCommands = mkExtraCommands releaseProfile;
    config = mkDockerConfig { isDev = false; };
  };

in
{
  # Default to dev image
  default = devImage;
  dev = devImage;
  release = releaseImage;

  # Expose metadata like docker-nixpkgs
  meta = {
    description = "FABulous container";
  };
}
