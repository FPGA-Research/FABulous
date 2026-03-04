# Custom GHDL derivation - build from source (for Linux)
{ lib, stdenv, gnat, zlib, which, pkg-config, patchelf
  # Version control parameters (provided by default.nix)
  , owner ? "ghdl", repo ? "ghdl", prefetchedSrc
}:

stdenv.mkDerivation rec {
  pname = "ghdl";
  version = "unstable";

  src = prefetchedSrc;

  nativeBuildInputs = [ pkg-config which gnat patchelf ];

  buildInputs = [ zlib ];

  # GHDL uses a custom configure script, not autotools
  configureScript = "./configure";

  configureFlags = [
    "--enable-libghdl"
    "--enable-synth"
  ];

  enableParallelBuilding = true;

  # GHDL's configure uses printf without format strings
  hardeningDisable = [ "format" ];

  preConfigure = ''
    chmod +x configure
    export PATH=${gnat}/bin:$PATH
  '';

  # Eliminate GNAT from the runtime closure (~830 MiB) by copying only the two
  # shared libraries GHDL actually needs (libgnat and libgcc_s) into $out/lib,
  # then rewriting RPATHs to point there instead of into the Nix store.
  #
  # Dependency chain being broken:
  #   gnat-wrapper -> gnat (372 MiB) -> gnat-bootstrap (462 MiB)
  #   gnat-lib (9 MiB) -> gnat-bootstrap (462 MiB)
  disallowedReferences = [ gnat gnat.cc gnat.cc.lib ];
  postInstall = let
    gnatUnwrapped = gnat.cc;
    gnatLib = gnat.cc.lib;
    gnatLibgcc = gnat.cc.libgcc;
  in ''
    # Remove .link files that contain hardcoded paths to libgnat.a
    find $out -name '*.link' -delete

    # Copy runtime libraries into $out/lib
    adalib=$(find ${gnatUnwrapped}/lib/gcc -name adalib -type d | head -1)
    for f in "$adalib"/libgnat-*.so; do
      cp "$f" "$out/lib/"
    done
    cp "${gnatLibgcc}/lib/libgcc_s.so.1" "$out/lib/"
    chmod u+w "$out"/lib/libgnat-*.so "$out"/lib/libgcc_s.so.1

    # Rewrite RPATHs on all ELF files: remove gnat entries, prepend $out/lib
    for f in "$out"/bin/* "$out"/lib/*.so "$out"/lib/*.so.*; do
      [ -L "$f" ] && continue
      [ ! -f "$f" ] && continue
      old_rpath=$(patchelf --print-rpath "$f" 2>/dev/null) || continue
      new_rpath=$(echo "$old_rpath" | tr ':' '\n' \
        | grep -v "${gnat}" \
        | grep -v "${gnatUnwrapped}" \
        | grep -v "${gnatLib}" \
        | tr '\n' ':' | sed 's/:$//')
      patchelf --set-rpath "$out/lib:$new_rpath" "$f"
    done

    # Scrub any remaining gnat store-path references from text files
    find $out -type f ! -name '*.so' ! -name '*.so.*' -exec \
      sed -i -e "s|${gnat}|/removed-build-ref|g" \
             -e "s|${gnatUnwrapped}|/removed-build-ref|g" \
             -e "s|${gnatLib}|/removed-build-ref|g" {} + 2>/dev/null || true
  '';

  meta = with lib; {
    description = "GHDL - the open-source analyzer, compiler, and simulator for VHDL (source build)";
    homepage = "https://github.com/${owner}/${repo}";
    license = licenses.gpl2Plus;
    platforms = platforms.linux;
    maintainers = [ ];
  };
}
