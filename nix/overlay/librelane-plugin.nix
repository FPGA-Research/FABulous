# `librelane-plugin-fabulous`: FABulous built against librelane's own Python set,
# in the shape `librelane-shell` loads plugins in. It takes `librelane` as an
# argument, which the shell overrides with its configured build, and carries
# `includedTools` for the shell's PATH.
#
# Only this one name enters the Python set. The packages it needs that nixpkgs
# lacks, or ships too old, are built here and stay private, so they never shadow
# a nixpkgs package or the uv.lock-converted ones in `fabulous-python`. Their
# versions and sources come from uv.lock.
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

  # Pure-Python wheels, installed as uv.lock pins them.
  lockedWheel =
    name: dependencies: relaxedDependencies:
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
      pythonRelaxDeps = relaxedDependencies;
    };

  fabulous-fasm = lockedWheel "fabulous-fasm" [ pyfinal.textx ] [ ];

  fabulous-bit-gen = lockedWheel "fabulous-bit-gen" [
    pyfinal.loguru
    fabulous-fasm
  ] [ ];

  # FABulous needs cmd2 4. nixpkgs ships 3, which nothing in librelane's closure
  # uses, so the newer one stays local to the plugin. Every cmd2 4 release asks
  # for rich>=15 and a newer prompt-toolkit than librelane's closure carries,
  # and one interpreter holds only one copy of each, so those bounds are relaxed.
  cmd2 =
    lockedWheel "cmd2"
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
      # `vcs-versioning` is listed as a build requirement but is not in nixpkgs.
      # The pretend version below makes setuptools-scm skip it.
      pypaBuildFlags = [ "--skip-dependency-check" ];
      env.SETUPTOOLS_SCM_PRETEND_VERSION = entry.version;
      dependencies = [ pyfinal.ply ];
      # Declared but never imported by `sdf_timing`.
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
      # pyproject.toml asks for setuptools>=83. nixpkgs ships 80, which builds
      # the same wheel.
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
        cmd2
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
      # numpy and bitarray come from librelane's set, below the bounds
      # dependabot raised in pyproject.toml. numpy cannot move without
      # rebuilding librelane's closure. uv only drives `FABulous plugins
      # install`, which cannot write into a store environment anyway.
      pythonRelaxDeps = [
        "numpy"
        "bitarray"
        "uv"
      ];
      # Ships the `task` binary as a wheel. `go-task` from nixpkgs is on PATH
      # instead, where FABulous also looks for it.
      pythonRemoveDeps = [ "go-task-bin" ];

      pythonImportsCheck = [
        "fabulous"
        "librelane_plugin_fabulous"
      ];

      passthru.includedTools = fabulous-tools ++ [ go-task ];
    }
  ) { };
}
