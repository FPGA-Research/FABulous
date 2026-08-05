# Build fixups for the Python packages uv2nix resolves out of a uv.lock.
#
# uv.lock records *what* to install, never *how* to build it, so every package
# that resolves to an sdist has to be told its build system here. Everything
# else — versions, sources, hashes — comes from the lock and needs no Nix edit.
#
# Split in two because the two halves have different audiences:
#
#   deps   : third-party packages in FABulous's dependency closure. Safe to
#            apply to any workspace, so `mkFabulousPythonSet` hands it to
#            downstream projects building a venv from their own uv.lock.
#   source : FABulous's own source package. Meaningful only for a workspace
#            whose root *is* this repo; a downstream lock resolves
#            `fabulous-fpga` from a released wheel that needs none of it.
{ lib }:

let
  # uv.lock ships no build-system metadata, so an sdist arrives with nothing to
  # build it. `resolveBuildSystem` pulls the named backends out of the
  # pyproject-build-systems overlay.
  addBuildSystem =
    buildSystems: final: drv:
    drv.overrideAttrs (old: {
      nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ final.resolveBuildSystem buildSystems;
    });

  setuptoolsBuild = addBuildSystem {
    setuptools = [ ];
    wheel = [ ];
  };

  # about-time and alive-progress each install a top-level LICENSE. Both land at
  # the same path when the venv is assembled, and the collision fails the build.
  dropTopLevelLicense =
    _final: drv:
    drv.overrideAttrs (old: {
      postInstall = (old.postInstall or "") + ''
        rm -f $out/LICENSE
      '';
    });

  setuptoolsScmBuild =
    final: drv:
    (addBuildSystem {
      setuptools = [ ];
      setuptools-scm = [ ];
      wheel = [ ];
    } final drv).overrideAttrs
      (old: {
        # setuptools_scm derives the version from git metadata, which the
        # fetched source tree does not carry. Take the version uv.lock already
        # resolved rather than a literal: a hand-written one goes stale on the
        # next `uv lock` without failing anything (this read 0.0.post134 while
        # the lock said 0.0.post136).
        env = (old.env or { }) // {
          SETUPTOOLS_SCM_PRETEND_VERSION = old.version;
        };
      });

  # Every package `deps` patches. `checks.python-fixups` asserts each still
  # resolves from uv.lock — a rename upstream otherwise turns a fixup into a
  # silent no-op rather than an error (see the check in flake.nix).
  depFixups = {
    about-time = dropTopLevelLicense;
    alive-progress = dropTopLevelLicense;
    librelane = setuptoolsBuild;
    pyperclip = setuptoolsBuild;
    sdf-timing = setuptoolsScmBuild;
  };

  # Reapplied after `toNixpkgs` conversion. That conversion reinstalls each
  # package from the wheel the uv2nix build produced, so anything a fixup did in
  # `postInstall` is undone — only changes baked into the wheel survive. These
  # two collide on a file the wheel legitimately contains, so they need fixing
  # on both sides.
  nixpkgsFixups = [
    "about-time"
    "alive-progress"
  ];

  fallbackVersion =
    (builtins.fromTOML (builtins.readFile ../../pyproject.toml)).tool.setuptools_scm.fallback_version;

  # `FABulous` and `fabulous` are declared as two console scripts, so an
  # installer generates two files. On a case-insensitive store those are one
  # path, and nixpkgs' wheel installer raises rather than overwrite, which is
  # what fails the build there. Ship the wheel with only the canonical name and
  # put the alias back as a symlink: it collapses onto the original where the
  # two collide, so the same expression works on either kind of store.
  #
  # The grep is the guard — if the entry point is ever renamed this fails here
  # rather than silently leaving the collision in place.
  dropAliasScript = ''
    grep -q '^fabulous = "fabulous.fabulous:main"$' pyproject.toml
    sed -i '/^fabulous = "fabulous.fabulous:main"$/d' pyproject.toml
  '';

  restoreAliasScript = ''
    [ -e "$out/bin/fabulous" ] || ln -s FABulous "$out/bin/fabulous"
  '';
in
{
  patchedPackages = lib.attrNames depFixups ++ nixpkgsFixups;

  # nixpkgs' own buildPythonPackage bootstrap is built *from* these, so
  # converting them deadlocks it: the converted package would need itself to
  # build. They stay at nixpkgs' versions, which is the one place the Python set
  # departs from uv.lock. All three are build tooling rather than anything
  # FABulous imports, and nixpkgs' versions satisfy its constraints.
  bootstrapPackages = [
    "wheel"
    "packaging"
    "tomli"
  ];

  deps =
    final: prev:
    # Applied only where the package is present. Which packages a lock resolves
    # is a property of the workspace, and a downstream one legitimately differs,
    # so absence is not an error *here* — `checks.python-fixups` is what holds
    # this list to FABulous's own lock.
    lib.mapAttrs (name: fixup: fixup final prev.${name}) (
      lib.filterAttrs (name: _: prev ? ${name}) depFixups
    );

  # Applied to the *nixpkgs* Python set, after `toNixpkgs` has converted the
  # uv2nix packages into it.
  nixpkgs =
    final: prev:
    lib.genAttrs nixpkgsFixups (name: dropTopLevelLicense final prev.${name})
    // {
      # The conversion reinstalls from the wheel, which discards the alias the
      # uv2nix build symlinked in, so it has to be recreated on this side too.
      fabulous-fpga = prev.fabulous-fpga.overrideAttrs (old: {
        postInstall = (old.postInstall or "") + restoreAliasScript;
      });
    };

  source = _final: prev: {
    fabulous-fpga = prev.fabulous-fpga.overrideAttrs (old: {
      # setuptools_scm cannot read a git tag from the sandboxed source copy, so
      # the build stamps pyproject.toml's fallback_version. Relabel the
      # derivation to match; src is untouched, so opt out of nixpkgs'
      # version/src mismatch warning.
      version = fallbackVersion;
      __intentionallyOverridingVersion = true;
      env = (old.env or { }) // {
        SETUPTOOLS_SCM_PRETEND_VERSION = fallbackVersion;
      };
      postPatch = (old.postPatch or "") + dropAliasScript;
      postInstall = (old.postInstall or "") + restoreAliasScript;
    });
  };
}
