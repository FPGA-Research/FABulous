final: prev: {

  openroad = prev.openroad.overrideAttrs (finalAttrs: previousAttrs: {
    patches = (previousAttrs.patches or []) ++ [../patches/openroad/fix_connect_by_abutment.patch];
  });

}