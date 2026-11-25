{ lib }:

let
  addBuildSystem =
    buildSystems: final: drv:
    drv.overrideAttrs (old: {
      nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ final.resolveBuildSystem buildSystems;
    });

  setuptoolsBuild = addBuildSystem {
    setuptools = [ ];
    wheel = [ ];
  };

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
        env = (old.env or { }) // {
          SETUPTOOLS_SCM_PRETEND_VERSION = old.version;
        };
      });

  depFixups = {
    about-time = dropTopLevelLicense;
    alive-progress = dropTopLevelLicense;
    librelane = addBuildSystem {
      setuptools = [ ];
      wheel = [ ];
      poetry-core = [ ];
    };
    pyperclip = setuptoolsBuild;
    sdf-timing = setuptoolsScmBuild;
  };

  nixpkgsFixups = [
    "about-time"
    "alive-progress"
  ];

  fallbackVersion =
    (builtins.fromTOML (builtins.readFile ../../pyproject.toml)).tool.setuptools_scm.fallback_version;

  dropAliasScript = ''
    grep -q '^fabulous = "fabulous.fabulous:main"$' pyproject.toml
    sed -i '/^fabulous = "fabulous.fabulous:main"$/d' pyproject.toml
  '';

  restoreAliasScript = ''
    [ -e "$out/bin/fabulous" ] || ln -s FABulous "$out/bin/fabulous"
  '';
in
{
  inherit fallbackVersion dropAliasScript restoreAliasScript;

  patchedPackages = lib.attrNames depFixups ++ nixpkgsFixups;

  bootstrapPackages = [
    "wheel"
    "packaging"
    "tomli"
  ];

  deps =
    final: prev:
    lib.mapAttrs (name: fixup: fixup final prev.${name}) (
      lib.filterAttrs (name: _: prev ? ${name}) depFixups
    );

  nixpkgs =
    final: prev:
    lib.genAttrs nixpkgsFixups (name: dropTopLevelLicense final prev.${name})
    // {
      fabulous-fpga = prev.fabulous-fpga.overrideAttrs (old: {
        postInstall = (old.postInstall or "") + restoreAliasScript;
      });
    };

  source = _final: prev: {
    fabulous-fpga = prev.fabulous-fpga.overrideAttrs (old: {
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
