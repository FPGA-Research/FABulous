{
  description = "FABulous EDA development environment with Nix - includes GHDL, Yosys, NextPNR, Librelane, and more";

  inputs = {
    # Pinned to nix-eda 6.2.0's nixpkgs for binary cache hits from fossi-foundation
    nixpkgs.url = "github:nixos/nixpkgs/b3aad468604d3e488d627c0b43984eb60e75e782";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nix-eda = {
      url = "github:fossi-foundation/nix-eda/6.2.0";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    librelane = {
      url = "github:librelane/librelane/dev";
      inputs.nix-eda.follows = "nix-eda";
    };

    # Prebuilt GHDL v6.0.0 binary tarballs (locked in flake.lock)
    ghdl-bin-x86_64-linux = {
      url = "https://github.com/ghdl/ghdl/releases/download/v6.0.0/ghdl-mcode-6.0.0-ubuntu24.04-x86_64.tar.gz";
      flake = false;
    };
    ghdl-bin-aarch64-darwin = {
      url = "https://github.com/ghdl/ghdl/releases/download/v6.0.0/ghdl-llvm-jit-6.0.0-macos15-aarch64.tar.gz";
      flake = false;
    };
    nextpnr-src = {
      url = "github:YosysHQ/nextpnr/nextpnr-0.9";
      flake = false;
    };
    fabulator-src = {
      url = "github:FPGA-Research/FABulator/beccd4e4c58b9fc92fafaf082883c20367dbe5ba";
      flake = false;
    };
  };

  nixConfig = {
    extra-substituters = [
      "https://nix-cache.fossi-foundation.org"
    ];
    extra-trusted-public-keys = [
      "nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs="
    ];
  };

  outputs =
    {
      nixpkgs,
      nix-eda,
      librelane,
      ghdl-bin-x86_64-linux,
      ghdl-bin-aarch64-darwin,
      nextpnr-src,
      fabulator-src,
      pyproject-nix,
      uv2nix,
      pyproject-build-systems,
      ...
    }:
    let
      inherit (nixpkgs) lib;
      forAllSystems = lib.genAttrs lib.systems.flakeExposed;

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      # Custom Python package overlay for packages that need special handling
      pyproject_pkg_overlay = import ./nix/overlay/python.nix;

      editableOverlay = workspace.mkEditablePyprojectOverlay {
        root = "$REPO_ROOT";
      };

      pythonSets = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = nixpkgs.legacyPackages.${system}.python312;
        in
        (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.wheel
              overlay
              pyproject_pkg_overlay
            ]
          )
      );

      devshell-overlay = librelane.inputs.devshell;
      nix_eda_pkgs = nix-eda.forAllSystems (
        system:
        import nix-eda.inputs.nixpkgs {
          inherit system;
          overlays = [
            nix-eda.overlays.default
            devshell-overlay.overlays.default
            librelane.overlays.default
          ];
        }
      );

    in
    {
      packages = forAllSystems (system: {
        default = pythonSets.${system}.mkVirtualEnv "FABulous-env" workspace.deps.default;
      });
      devShells = forAllSystems (
        system:
        let
          # Use the per-system package set built above so mkShell and all
          # overlays (including librelane and project overlays) are present.
          pkgs = nix_eda_pkgs.${system};
          pythonSet = pythonSets.${system}.overrideScope editableOverlay;

          # Create virtualenv with all deps
          virtualenv = pythonSet.mkVirtualEnv "FABulous-env" workspace.deps.all;

          customPkgs = import ./nix {
            inherit pkgs;
            srcs = {
              ghdl-linux-bin = ghdl-bin-x86_64-linux;
              ghdl-darwin-bin = ghdl-bin-aarch64-darwin;
              nextpnr = nextpnr-src;
              fabulator = fabulator-src;
            };
          };

          # Get librelane from our patched pkgs (which includes our overlays)
          librelane-pkg = pkgs.python3.pkgs.librelane;
          # We need librelane's Python modules available for the EDA tools, but we don't
          # want to include the full librelane-env in packages (would collide with virtualenv).
          # Instead, we'll add it to NIX_PYTHONPATH.
          librelane-python-path = "${librelane-pkg}/${pkgs.python3.sitePackages}";
          tkinter-pkg = nixpkgs.legacyPackages.${system}.python312Packages.tkinter;
          tkinter-python-path = "${tkinter-pkg}/${nixpkgs.legacyPackages.${system}.python312.sitePackages}";

          # Combine all packages: librelane tools (with patched OpenROAD) + our custom tools + uv2nix env
          # Note: We only include virtualenv for Python, not librelane-env, to avoid collisions
          # Filter by platform support: include if no platforms specified or current system matches
          systemSupported =
            tool:
            let
              platforms = tool.meta.platforms or [ ];
            in
            platforms == [ ] || (builtins.elem system platforms);

          allPackages = [
            virtualenv
            pkgs.uv
            pkgs.which
            pkgs.git
            pkgs.fish
            pkgs.zsh
            pkgs.gtkwave
            customPkgs.nextpnr
            customPkgs.fabulator
            customPkgs.ghdl
          ]
          ++ (builtins.filter systemSupported librelane-pkg.includedTools);

          prompt = ''\[\033[1;32m\][FABulous-nix:\w]\$\[\033[0m\] '';
        in
        let
          # Common devshell configuration (bash by default)
          baseShellConfig = {
            devshell.packages = allPackages;
            env = [
              {
                name = "NIX_PYTHONPATH";
                value = "${librelane-python-path}:${tkinter-python-path}";
              }
              {
                name = "PYTHONWARNINGS";
                value = "ignore:Importing fasm.parse_fasm:RuntimeWarning,ignore:Falling back on slower textX parser implementation:RuntimeWarning";
              }
              {
                name = "UV_NO_SYNC";
                value = "1";
              }
              {
                name = "UV_PYTHON";
                value = pythonSet.python.interpreter;
              }
              {
                name = "UV_PYTHON_DOWNLOADS";
                value = "never";
              }
              {
                name = "PYTHONNOUSERSITE";
                value = "1";
              }
            ];
            devshell.startup.fabulous-setup = {
              text = ''

                export REPO_ROOT=$(git rev-parse --show-toplevel)
                ORIGINAL_PS1="$PS1"

                . ${virtualenv}/bin/activate
                # Restore original PS1 to avoid double prompt decoration
                export PS1="$ORIGINAL_PS1"

                # Ensure the repository root and the virtualenv site-packages are importable
                VENV_SITE=$(python -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)

                # Build PYTHONPATH: NIX_PYTHONPATH (librelane) + venv + repo root
                if [ -n "$VENV_SITE" ]; then
                  export PYTHONPATH="$NIX_PYTHONPATH:$VENV_SITE:$REPO_ROOT"
                else
                  export PYTHONPATH="$NIX_PYTHONPATH:$REPO_ROOT"
                fi

              '';
            };
            devshell.interactive.PS1 = {
              text = ''PS1="${prompt}"'';
            };
            motd = "";
          };
        in
        {
          # Default: bash
          default = pkgs.devshell.mkShell baseShellConfig;

          # Start in fish: nix develop .#fish
          fish = pkgs.devshell.mkShell (
            baseShellConfig
            // {
              devshell.interactive."zzz-switch-shell" = {
                # Run last so we exec into fish after env is set up
                text = "exec fish -l";
              };
            }
          );

          # Start in zsh: nix develop .#zsh
          zsh = pkgs.devshell.mkShell (
            baseShellConfig
            // {
              devshell.interactive."zzz-switch-shell" = {
                text = "exec zsh -l";
              };
            }
          );
        }
      );

    };
}
