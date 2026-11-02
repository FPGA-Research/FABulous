# FABulous's contribution to a nixpkgs instance: the pinned EDA tools, the
# uv.lock-built Python environment, the wrapped application, and the shell that
# downstream projects compose from.
#
# Applied as `fabulous.overlays.default`, so everything below is built against
# the consumer's own nixpkgs and stays reachable through the normal
# `.override` / `.overrideAttrs` surface. The factory arguments are the flake
# inputs that cannot be expressed inside a package file: the pinned tool sources
# and the uv2nix plumbing that turns uv.lock into a Python environment.
{
  srcs,
  workspace,
  # Names of every package uv.lock resolved. Read from the lock rather than
  # listed here, so it tracks `uv lock` with no Nix edit.
  lockedPackages,
  # Build fixups from `./python.nix`.
  pythonFixups,
  uv2nix,
  pyproject-nix,
  pyproject-build-systems,
}:

final: prev:

let
  inherit (final) lib;

  hacks = final.callPackages pyproject-nix.build.hacks { };

  # nixpkgs' convention for a VCS pin with no upstream release. Derived from the
  # flake input's lock timestamp so `nix flake update` yields a comparable
  # version rather than a permanent "unstable".
  unstableVersion =
    src:
    let
      d = src.lastModifiedDate;
    in
    "0-unstable-${lib.substring 0 4 d}-${lib.substring 4 2 d}-${lib.substring 6 2 d}";

  # Tool sources must be commit pins. yosys stamps `rev` into its version, and
  # an override without one would otherwise fail deep inside a build.
  pinned =
    name: src:
    if src ? rev && builtins.match "[0-9a-f]{40}" src.rev != null then
      src
    else
      throw "${name}: source is not pinned to a commit SHA (rev = ${src.rev or "none"}). Override it with a git or github input.";
in
{
  # Parameterised over the workspace rather than closed over FABulous's own:
  # a downstream project passes the workspace for *its* uv.lock (which resolves
  # `fabulous-fpga` alongside its own dependencies) and gets one coherent venv
  # whose versions uv resolved across both projects at once.
  mkFabulousPythonSet =
    {
      workspace,
      # Wheels carry their build already, so preferring them is what keeps the
      # fixup list in `python.nix` short.
      sourcePreference ? "wheel",
      # Extra uv2nix overlays, applied last: the caller's own build fixups, or
      # `workspace.mkEditablePyprojectOverlay` for an editable checkout.
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

  # Re-exported so a downstream flake needs FABulous as its only input instead
  # of also pinning uv2nix, pyproject-nix and build-system-pkgs in step with it.
  # A mismatch there surfaces as an obscure eval error.
  loadFabulousWorkspace =
    workspaceRoot: uv2nix.lib.workspace.loadWorkspace { inherit workspaceRoot; };

  # uv.lock is the single source of truth for FABulous's Python world. Building
  # the set from `final` (rather than a second nixpkgs instance) keeps the venv's
  # interpreter identical to the one the rest of this overlay uses.
  fabulous-python-set = final.mkFabulousPythonSet {
    inherit workspace;
    # Stamps the version onto a `fabulous-fpga` built from source. A lock that
    # resolves `fabulous-fpga` to a released wheel needs none of it.
    overrides = [ pythonFixups.source ];
  };

  # An ordinary nixpkgs Python whose package set is uv.lock's, so FABulous
  # composes the way any other Python package does (`withPackages`,
  # `propagatedBuildInputs`, `.override`) instead of only as a sealed
  # virtualenv.
  #
  # The versions still come from uv.lock: `toNixpkgs` resolves each converted
  # package's dependencies from the set it is applied to, so converting the whole
  # closure at once is what keeps uv's resolution rather than nixpkgs'. Scoping
  # it to this interpreter (rather than overlaying `pkgs.python3`) is what stops
  # that from replacing packages for everything else in the nixpkgs instance.
  fabulous-python =
    let
      converted = hacks.toNixpkgs {
        pythonSet = final.fabulous-python-set;
        # Named explicitly, because build-system-pkgs adds entries absent from
        # the lock (`oldest-supported-numpy`) that fail to evaluate.
        packages = lib.subtractLists pythonFixups.bootstrapPackages lockedPackages;
      };
      python = final.python3.override {
        packageOverrides = lib.composeExtensions converted pythonFixups.nixpkgs;
        # buildPythonPackage resolves dependencies through `self`, so without
        # this the converted packages would pull their deps from the unmodified
        # nixpkgs set and land back on nixpkgs' versions.
        inherit self;
      };
      self = python;
    in
    python;

  # What the `fabulous` wrapper runs: FABulous plus tkinter, which the CLI
  # imports at startup and which is not a uv.lock dependency because it ships
  # with CPython everywhere except nixpkgs.
  fabulous-python-env = final.fabulous-python.withPackages (ps: [
    ps.fabulous-fpga
    ps.tkinter
  ]);

  # GHDL ships prebuilt tarballs rather than a source build, keyed by system so
  # only the one for this platform is fetched.
  fab-ghdl = final.callPackage ../tools/ghdl-bin.nix {
    src =
      srcs.ghdl-bin.${final.stdenv.hostPlatform.system}
        or (throw "fab-ghdl: no prebuilt GHDL tarball for ${final.stdenv.hostPlatform.system}");
  };

  # Bundles the ghdl-yosys-plugin so `fab-yosys -m ghdl` works with no wrapper.
  # Installed under a `fab-` prefix so it never collides with a system yosys.
  fab-yosys = final.callPackage ../tools/yosys.nix {
    src = pinned "fab-yosys" srcs.yosys;
    version = unstableVersion srcs.yosys;
    ghdl-bin = final.fab-ghdl;
    ghdlYosysPluginSrc = srcs.ghdl-yosys-plugin;
  };

  # Prefixed so composing this overlay does not silently replace nixpkgs'
  # nextpnr; the installed binary is still `nextpnr-generic`.
  fab-nextpnr = final.callPackage ../tools/nextpnr.nix {
    src = pinned "fab-nextpnr" srcs.nextpnr;
    version = unstableVersion srcs.nextpnr;
  };

  fabulator = final.callPackage ../tools/fabulator.nix {
    src = pinned "fabulator" srcs.fabulator;
    version = unstableVersion srcs.fabulator;
  };

  fabulous = final.callPackage ../package.nix { };

  fabulous-shell = final.callPackage ../create-shell.nix { };
}
