{
  description = "hello world application using uv2nix";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    nixpkgs-stable = {
      url = "github:nixos/nixpkgs/nixos-25.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };

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
    librelane.url = "github:librelane/librelane/dev";

    # Tag-pinned sources for custom tools (locked in flake.lock)
    ghdl-src = {
      url = "github:ghdl/ghdl/nightly";
      flake = false;
    };
    nextpnr-src = {
      url = "github:YosysHQ/nextpnr/nextpnr-0.9";
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
      nixpkgs-stable,
      librelane,
      ghdl-src,
      nextpnr-src,
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
      pyproject_pkg_overlay = final: prev: {
        # Override fasm to use GitHub source instead of PyPI and add missing build deps
        fasm = prev.fasm.overrideAttrs (old: {
          # Use GitHub source for better compatibility
          src = final.pkgs.fetchFromGitHub {
            owner = "chipsalliance";
            repo = "fasm";
            rev = "v0.0.2";
            sha256 = "sha256-AMG4+qMk2+40GllhE8UShagN/jxSVN+RNtJCW3vFLBU=";
          };
          # Add required build dependencies that may be missing
          nativeBuildInputs = (old.nativeBuildInputs or []) ++ final.resolveBuildSystem {
            setuptools = [ ]; wheel = [ ]; cython = [ ];
          };
        });

        pyperclip = prev.pyperclip.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or []) ++ final.resolveBuildSystem {
            setuptools = [ ]; wheel = [ ];
          };
        });
        librelane = prev.librelane.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or []) ++ final.resolveBuildSystem {
            setuptools = [ ]; wheel = [ ];
          };
        });
      };

      editableOverlay = workspace.mkEditablePyprojectOverlay {
        root = "$REPO_ROOT";
      };

      pythonSets = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};

          # I can only get Tkinter support by using python3Full from nixpkgs-stable
          python = nixpkgs-stable.legacyPackages.${system}.python312Full;
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

      nix-eda = librelane.inputs.nix-eda;
      nix_eda_overlays = {
        default = import ./nix/overlay.nix;
      };
      devshell-overlay = librelane.inputs.devshell;
      # Build a per-system package set that already includes the EDA and
      # librelane overlays plus our project overlays so downstream code can
      # simply pick the per-system `pkgs` and find attributes like mkShell.
      # IMPORTANT: Use nix-eda's nixpkgs (not our nixos-unstable) to match the gcc version
      nix_eda_pkgs = nix-eda.forAllSystems (system:
        import nix-eda.inputs.nixpkgs {
          inherit system;
          overlays = [
            nix-eda.overlays.default
            devshell-overlay.overlays.default
            librelane.overlays.default
            nix_eda_overlays.default
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

          # pass the current pkgs to the nix overlay so it returns a package set
          # also pass flake-locked sources so tags resolve to a fixed commit
          customPkgs = import ./nix {
            inherit pkgs;
            srcs = {
              ghdl = ghdl-src;
              nextpnr = nextpnr-src;
            };
          };

          # Get librelane from our patched pkgs (which includes our overlays)
          librelane-pkg = pkgs.python3.pkgs.librelane;
          # We need librelane's Python modules available for the EDA tools, but we don't
          # want to include the full librelane-env in packages (would collide with virtualenv).
          # Instead, we'll add it to NIX_PYTHONPATH.
          librelane-python-path = "${librelane-pkg}/${pkgs.python3.sitePackages}";

          # Combine all packages: librelane tools (with patched OpenROAD) + our custom tools + uv2nix env
          # Note: We only include virtualenv for Python, not librelane-env, to avoid collisions
          allPackages =
            [
              virtualenv
              pkgs.uv
              pkgs.which
              pkgs.git
              pkgs.zsh

              pkgs.delta
              pkgs.gtkwave
              pkgs.coreutils
              pkgs.graphviz
              customPkgs.nextpnr
              customPkgs.ghdl
            ]
            ++ librelane-pkg.includedTools; # This includes patched OpenROAD, yosys, klayout, etc.

          prompt = ''\[\033[1;32m\][FABulous-nix:\w]\$\[\033[0m\] '';
        in
        {
          default = pkgs.devshell.mkShell {
            devshell.packages = allPackages;
            env = [
              {
                name = "NIX_PYTHONPATH";
                value = "${librelane-python-path}";
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

                echo "[FABulous shell] PYTHONPATH: $PYTHONPATH" >&2
                echo "[FABulous shell] Python: $(which python)" >&2
                echo "[FABulous shell] Python version: $(python --version)" >&2
                echo "[FABulous shell] OpenROAD: $(which openroad)" >&2
              '';
            };
            devshell.interactive.PS1 = {
              text = ''PS1="${prompt}"'';
            };
            motd = "";
          };
        }
      );

    };
}
