{
  description = "FABulous EDA development environment with Nix - includes GHDL, Yosys, NextPNR, Librelane, and more.
    nix-eda and nixpkgs follow librelane's pins for binary cache compatibility.";

  inputs = {
    librelane.url = "github:librelane/librelane";

    # Follow librelane's nix-eda and nixpkgs for binary cache hits
    nix-eda.follows = "librelane/nix-eda";
    nixpkgs.follows = "librelane/nix-eda/nixpkgs";

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

    # Prebuilt GHDL v6.0.0 binary tarballs (locked in flake.lock)
    ghdl-bin-x86_64-linux = {
      url = "https://github.com/ghdl/ghdl/releases/download/v6.0.0/ghdl-mcode-6.0.0-ubuntu24.04-x86_64.tar.gz";
      flake = false;
    };
    ghdl-bin-aarch64-darwin = {
      url = "https://github.com/ghdl/ghdl/releases/download/v6.0.0/ghdl-llvm-jit-6.0.0-macos15-aarch64.tar.gz";
      flake = false;
    };
    yosys-src = {
      url = "git+https://github.com/YosysHQ/yosys?submodules=1";
      flake = false;
    };
    # ghdl-yosys-plugin tracks ghdl master and has no GitHub releases, only a
    # `ghdl-v<X>` tag that lines up with each ghdl release. Pin to the tag
    # matching our ghdl-bin version; bumping ghdl-bin should bump this in
    # lockstep.
    ghdl-yosys-plugin-src = {
      url = "github:ghdl/ghdl-yosys-plugin/ghdl-v6.0.0";
      flake = false;
    };
    nextpnr-src = {
      url = "github:YosysHQ/nextpnr";
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
      self,
      nixpkgs,
      nix-eda,
      librelane,
      ghdl-bin-x86_64-linux,
      ghdl-bin-aarch64-darwin,
      yosys-src,
      ghdl-yosys-plugin-src,
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
          python = nixpkgs.legacyPackages.${system}.python3;
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

      fabulousToolchain = forAllSystems (
        system:
        let
          pkgs = nix_eda_pkgs.${system};
          customPkgs = import ./nix {
            inherit pkgs;
            srcs = {
              ghdl-linux-bin = ghdl-bin-x86_64-linux;
              ghdl-darwin-bin = ghdl-bin-aarch64-darwin;
              yosys = yosys-src;
              ghdl-yosys-plugin = ghdl-yosys-plugin-src;
              nextpnr = nextpnr-src;
              fabulator = fabulator-src;
            };
          };
          librelane-pkg = pkgs.python3.pkgs.librelane;
          tkinter-pkg = nixpkgs.legacyPackages.${system}.python3Packages.tkinter;
          tkinter-python-path = "${tkinter-pkg}/${nixpkgs.legacyPackages.${system}.python3.sitePackages}";
          systemSupported =
            tool:
            let
              platforms = tool.meta.platforms or [ ];
            in
            platforms == [ ] || (builtins.elem system platforms);
          toolPackages = [
            pkgs.uv
            pkgs.which
            pkgs.git
            pkgs.fish
            pkgs.zsh
            pkgs.gtkwave
            customPkgs.yosys
            customPkgs.nextpnr
            customPkgs.fabulator
            customPkgs.ghdl
            pkgs.nvc
          ]
          ++ (builtins.filter systemSupported librelane-pkg.includedTools);
        in
        {
          inherit
            pkgs
            customPkgs
            librelane-pkg
            tkinter-python-path
            toolPackages
            ;
          # Runtime environment shared by the wrapped package and the dev shells.
          envVars = {
            # Tells FABulous the nix yosys binary is named fab-yosys.
            FAB_YOSYS_PATH = "fab-yosys";
            # libghdl, dlopen'd by the yosys ghdl plugin, can't derive its own
            # install prefix (only the ghdl binary can), so it needs this to
            # find the IEEE libraries.
            GHDL_PREFIX = "${customPkgs.ghdl}/lib/ghdl";
            # Silence known third-party import warnings (fasm, textX).
            PYTHONWARNINGS = "ignore:Importing fasm.parse_fasm:RuntimeWarning,ignore:Falling back on slower textX parser implementation:RuntimeWarning";
          };
        }
      );

    in
    {
      packages = forAllSystems (
        system:
        let
          tc = fabulousToolchain.${system};
          virtualenv = pythonSets.${system}.mkVirtualEnv "FABulous-env" workspace.deps.default;
          fabulousApp = import ./nix/package.nix {
            inherit lib virtualenv;
            pkgs = tc.pkgs;
            toolchain = tc;
          };
        in
        {
          default = fabulousApp;
          fabulous = fabulousApp;
        }
      );
      devShells = forAllSystems (
        system:
        let
          tc = fabulousToolchain.${system};
          pythonSet = pythonSets.${system}.overrideScope editableOverlay;
        in
        import ./nix/devshells.nix {
          inherit lib;
          pkgs = tc.pkgs;
          toolchain = tc;
          virtualenv = pythonSet.mkVirtualEnv "FABulous-env" workspace.deps.all;
          pythonInterpreter = pythonSet.python.interpreter;
          repoRoot = ./.;
        }
      );

      # Consumer-facing composition surface. Downstream chip/fabric projects
      # build their shell from `mkConsumerShell { extraPackages = ...; extraPythonPackages = ...; }`
      # (a hermetic uv.lock-pinned FABulous + librelane + plugin, plus their own
      # non-Python tools and Python packages).
      lib = forAllSystems (
        system:
        let
          tc = fabulousToolchain.${system};
          consumerVenv = pythonSets.${system}.mkVirtualEnv "FABulous-consumer-env" workspace.deps.default;
        in
        {
          mkConsumerShell = import ./nix/consumer.nix {
            pkgs = tc.pkgs;
            python = nixpkgs.legacyPackages.${system}.python3;
            toolchain = tc;
            virtualenv = consumerVenv;
          };
        }
      );

      overlays.default = final: prev: {
        fabulous = self.packages.${final.system}.default;
      };

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/FABulous";
        };
        librelane = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/librelane";
        };
      });

    };
}
