{
  uvLock,
  pythonFixups,
  fabulous-tools,
  go-task,
  src,
}:

pyfinal: _pyprev:

let
  locked =
    name:
    let
      matches = builtins.filter (p: p.name == name) uvLock.package;
    in
    if builtins.length matches == 1 then
      builtins.head matches
    else
      throw "librelane-plugin-fabulous: uv.lock resolves ${toString (builtins.length matches)} entries named ${name}, expected 1.";

  lockedPurePythonWheel =
    name: dependencies: boundsAboveLibrelaneClosure:
    let
      entry = locked name;
      wheel = builtins.head entry.wheels;
    in
    pyfinal.buildPythonPackage {
      pname = name;
      inherit (entry) version;
      format = "wheel";
      src = pyfinal.pkgs.fetchurl { inherit (wheel) url hash; };
      inherit dependencies;
      pythonRelaxDeps = boundsAboveLibrelaneClosure;
    };

  fabulous-fasm = lockedPurePythonWheel "fabulous-fasm" [ pyfinal.textx ] [ ];

  fabulous-bit-gen = lockedPurePythonWheel "fabulous-bit-gen" [
    pyfinal.loguru
    fabulous-fasm
  ] [ ];

  cmd2-v4 =
    lockedPurePythonWheel "cmd2"
      (with pyfinal; [
        prompt-toolkit
        pyperclip
        rich
        rich-argparse
      ])
      [
        "prompt-toolkit"
        "rich"
      ];

  sdf-timing =
    let
      entry = locked "sdf-timing";
      gitUrl = builtins.head (builtins.split "#" entry.source.git);
    in
    pyfinal.buildPythonPackage {
      pname = "sdf-timing";
      inherit (entry) version;
      pyproject = true;
      src = builtins.fetchGit {
        url = gitUrl;
        rev = builtins.elemAt (builtins.split "#" entry.source.git) 2;
        allRefs = true;
      };
      build-system = with pyfinal; [
        setuptools
        setuptools-scm
        wheel
      ];
      pypaBuildFlags = [ "--skip-dependency-check" ];
      env.SETUPTOOLS_SCM_PRETEND_VERSION = entry.version;
      dependencies = [ pyfinal.ply ];
      pythonRemoveDeps = [ "pyjson" ];
    };
in
{
  librelane-plugin-fabulous = pyfinal.callPackage (
    {
      buildPythonPackage,
      librelane,
      setuptools,
      setuptools-scm,
      wheel,
      tkinter,
      python-dotenv,
      loguru,
      requests,
      bitarray,
      pydantic,
      pydantic-settings,
      packaging,
      typer,
      pyyaml,
      pick,
      pymoo,
      numpy,
      dill,
      networkx,
      ciel,
      jinja2,
      uv,
      pluggy,
    }:
    buildPythonPackage {
      pname = "fabulous-fpga";
      version = pythonFixups.fallbackVersion;
      inherit src;
      pyproject = true;

      build-system = [
        setuptools
        setuptools-scm
        wheel
      ];
      pypaBuildFlags = [ "--skip-dependency-check" ];
      env.SETUPTOOLS_SCM_PRETEND_VERSION = pythonFixups.fallbackVersion;

      postPatch = pythonFixups.dropAliasScript;
      postInstall = pythonFixups.restoreAliasScript;

      dependencies = [
        librelane
        tkinter
        python-dotenv
        loguru
        requests
        cmd2-v4
        bitarray
        pydantic
        pydantic-settings
        packaging
        typer
        fabulous-bit-gen
        pyyaml
        pick
        pymoo
        numpy
        dill
        networkx
        sdf-timing
        ciel
        jinja2
        uv
        pluggy
      ];
      pythonRelaxDeps = [
        "numpy"
        "bitarray"
        "uv"
      ];
      pythonRemoveDeps = [ "go-task-bin" ];

      pythonImportsCheck = [
        "fabulous"
        "librelane_plugin_fabulous"
      ];

      passthru.includedTools = fabulous-tools ++ [ go-task ];
    }
  ) { };
}
