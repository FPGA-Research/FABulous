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
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    let
      inherit (nixpkgs) lib;

      # Only the systems a prebuilt GHDL tarball exists for. Claiming
      # `lib.systems.flakeExposed` would make `nix flake check` fail to evaluate
      # on the eight systems that have no toolchain.
      supportedSystems = [
        "x86_64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = lib.genAttrs supportedSystems;

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      # Resolves `fabulous` and the generated side-packages under $REPO_ROOT so
      # source edits apply without a rebuild. Dev shells only.
      editableOverlay = workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; };

      # Imported here as well as in the overlay, only so `checks` can see which
      # packages the fixups claim to patch. Pure, so evaluating it twice is free.
      pythonFixups = import ./nix/overlay/python.nix { inherit lib; };
    in
    {
      overlays.default = import ./nix/overlay {
        inherit
          workspace
          uv2nix
          pyproject-nix
          pyproject-build-systems
          ;
        lockedPackages = map (p: p.name) (lib.importTOML ./uv.lock).package;
        srcs = {
          ghdl-linux-bin = ghdl-bin-x86_64-linux;
          ghdl-darwin-bin = ghdl-bin-aarch64-darwin;
          yosys = yosys-src;
          ghdl-yosys-plugin = ghdl-yosys-plugin-src;
          nextpnr = nextpnr-src;
          fabulator = fabulator-src;
        };
      };

      # The composition surface downstream projects build on: a nixpkgs instance
      # carrying the EDA toolchain, librelane, and FABulous. A chip project adds
      # this flake as one input and takes `pkgs.fabulous-shell` from here.
      legacyPackages = forAllSystems (
        system:
        import nixpkgs {
          inherit system;
          overlays = [
            nix-eda.overlays.default
            librelane.inputs.devshell.overlays.default
            librelane.overlays.default
            self.overlays.default
          ];
        }
      );

      packages = forAllSystems (
        system:
        let
          pkgs = self.legacyPackages.${system};
        in
        {
          inherit (pkgs)
            fabulous
            fabulous-shell
            fab-yosys
            fab-nextpnr
            fab-ghdl
            fabulator
            ;
          default = pkgs.fabulous;
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = self.legacyPackages.${system};
        in
        import ./nix/devshells.nix {
          inherit lib pkgs;
          inherit (pkgs) fabulous fabulous-shell;
          editableVenv = (pkgs.fabulous-python-set.overrideScope editableOverlay).mkVirtualEnv "FABulous-env" workspace.deps.all;
          repoRoot = ./.;
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = self.legacyPackages.${system};

          # Every fixup in `nix/overlay/python.nix` must still name a package
          # uv.lock resolves. Nix only forces an override when something depends
          # on the package, so a rename upstream otherwise turns a fixup into a
          # silent no-op rather than an error — which is exactly what the `fasm`
          # fixup did after that package became `fabulous-fasm` (#672).
          stale = lib.filter (name: !(pkgs.fabulous-python-set ? ${name})) pythonFixups.patchedPackages;
        in
        self.packages.${system}
        // {
          devShell = self.devShells.${system}.default;

          python-fixups =
            if stale != [ ] then
              throw ''
                nix/overlay/python.nix patches ${lib.concatStringsSep ", " stale}, which uv.lock no longer resolves.
                Drop the fixup, or rename it to whatever the package is called now.
              ''
            else
              pkgs.runCommand "fabulous-python-fixups-current" { } "touch $out";
        }
      );

      # `nix flake init -t github:FPGA-Research/FABulous` scaffolds a project
      # that depends on FABulous: a uv workspace whose uv.lock resolves
      # `fabulous-fpga` next to the project's own Python dependencies.
      templates.default = {
        path = ./nix/templates/downstream;
        description = "A chip or fabric project built on FABulous, with its own uv.lock";
      };

      formatter = forAllSystems (system: nix-eda.formatter.${system});

      apps = forAllSystems (
        system:
        let
          pkgs = self.legacyPackages.${system};
        in
        {
          default = {
            type = "app";
            program = lib.getExe pkgs.fabulous;
          };
          librelane = {
            type = "app";
            program = "${pkgs.fabulous}/bin/librelane";
          };
        }
      );
    };
}
