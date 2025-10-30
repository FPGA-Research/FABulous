final: prev: {
    # Override fasm to use GitHub source instead of PyPI and add missing build deps
    fasm = prev.fasm.overrideAttrs (old: {
        src = final.pkgs.fetchFromGitHub {
        owner = "chipsalliance";
        repo = "fasm";
        rev = "v0.0.2";
        sha256 = "sha256-AMG4+qMk2+40GllhE8UShagN/jxSVN+RNtJCW3vFLBU=";
        };
        nativeBuildInputs = (old.nativeBuildInputs or []) ++ final.resolveBuildSystem {
        setuptools = [ ]; wheel = [ ]; cython = [ ];
        };
        propagatedBuildInputs = (old.propagatedBuildInputs or []) ++ [ prev.textx ];
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
    cocotb-test = prev.cocotb-test.overrideAttrs (old: {
        nativeBuildInputs = (old.nativeBuildInputs or []) ++ final.resolveBuildSystem {
        setuptools = [ ]; wheel = [ ];
        };
    });
    cocotb = prev.cocotb-test.overrideAttrs (old: {
        nativeBuildInputs = (old.nativeBuildInputs or []) ++ final.resolveBuildSystem {
        setuptools = [ ]; wheel = [ ];
        };
    });
}