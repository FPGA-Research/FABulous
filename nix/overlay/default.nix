{
  fabulator-src,
  workspace,
  lockedPackages,
  uvLock,
  pythonFixups,
  uv2nix,
  pyproject-nix,
  pyproject-build-systems,
}:

final: prev:

let
  inherit (final) lib;

  hacks = final.callPackages pyproject-nix.build.hacks { };

  unstableVersion =
    src:
    let
      d = src.lastModifiedDate;
    in
    "0-unstable-${lib.substring 0 4 d}-${lib.substring 4 2 d}-${lib.substring 6 2 d}";
in
{
  mkFabulousPythonSet =
    {
      workspace,
      sourcePreference ? "wheel",
      overrides ? [ ],
    }:
    (final.callPackage pyproject-nix.build.packages { python = final.python3; }).overrideScope (
      lib.composeManyExtensions (
        [
          pyproject-build-systems.overlays.wheel
          (workspace.mkPyprojectOverlay { inherit sourcePreference; })
          pythonFixups.deps
        ]
        ++ overrides
      )
    );

  loadFabulousWorkspace =
    workspaceRoot: uv2nix.lib.workspace.loadWorkspace { inherit workspaceRoot; };

  fabulous-python-set = final.mkFabulousPythonSet {
    inherit workspace;
    overrides = [ pythonFixups.source ];
  };

  fabulous-python =
    let
      converted = hacks.toNixpkgs {
        pythonSet = final.fabulous-python-set;
        packages = lib.subtractLists pythonFixups.bootstrapPackages lockedPackages;
      };
      python = final.python3.override {
        packageOverrides = lib.composeExtensions converted pythonFixups.nixpkgs;
        inherit self;
      };
      self = python;
    in
    python;

  fabulous-python-env = final.fabulous-python.withPackages (ps: [
    ps.fabulous-fpga
    ps.tkinter
  ]);

  fabulator = final.callPackage ../tools/fabulator.nix {
    src = fabulator-src;
    version = unstableVersion fabulator-src;
  };

  fabulous = final.callPackage ../package.nix { };

  fabulous-tools = final.callPackage ../tools.nix { };

  pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [
    (import ./librelane-plugin.nix {
      inherit uvLock pythonFixups;
      inherit (final) fabulous-tools go-task;
      src = final.fabulous-python-set.fabulous-fpga.src;
    })
  ];

  fabulous-shell = final.callPackage ../create-shell.nix { };
}
