# LibreLane plugin assets

Vendored assets used by the plugin translation tests
(`tests/gds_flow_test/flow_test/test_plugin_real_assets.py`) to drive the
`FABulousTile` and `FABulousFabric` adapters (the LibreLane plugin entry points
re-exported from `librelane_plugin_fabulous`) against realistic inputs.

## Layout

The directory tree mirrors the upstream `FPGA-Research/fabulous-tiles` repository so
the relative paths inside the vendored CSV/YAML files (`../common/`,
`../../../primitives/...`, `../../../models_pack.v`) resolve unmodified.

```
tests/assets/librelane_plugin/
├── README.md                     # this file
├── models_pack.v                 # symlink into the FABulous project template
├── primitives/                   # BEL libraries
│   └── FABULOUS_LC/fabulous/FABULOUS_LC.v
├── tiles/classic/                # tile library
│   ├── common/                   # shared per-direction wiring
│   │   ├── Base.csv
│   │   ├── Base.list
│   │   └── config.yaml
│   └── LUT4x8_ha/                # the one tile we harden
│       ├── LUT4x8_ha.csv
│       ├── LUT4x8_ha_switch_matrix.list
│       └── config.yaml           # FABulousTile flow config
└── fabrics/
    └── synthetic_lut4x8_ha_10x10/
        ├── synthetic_lut4x8_ha_10x10.csv  # 10x10 grid, all LUT4x8_ha
        └── config.yaml                    # FABulousFabric flow config
```

## Sources

| Path | Upstream repo | Commit pinned |
| --- | --- | --- |
| `tiles/`, `primitives/` | https://github.com/FPGA-Research/fabulous-tiles | `964c1ab38a4e0a85c190999fbba7dc2fa7aa667c` |
| `fabrics/synthetic_lut4x8_ha_10x10/` (synthetic, derived from upstream layout) | https://github.com/FPGA-Research/fabulous-fabrics | `bb5d98490fbc99f1f0662f072d3819b7a9b2d663` |

`models_pack.v` is a symlink into the FABulous project template
(`fabulous/fabric_files/FABulous_project_template_verilog/Fabric/models_pack.v`),
not a vendored copy, so it always tracks the in-repo primitive models.

The fabric is **synthetic** rather than vendored verbatim: the upstream
`classic_fabric_10x10` references 16 distinct tile types, but the nightly
hardens only `LUT4x8_ha`, so the fabric grid is filled entirely with that one
tile to exercise the stitching code path.

When the rest of the upstream tile library is hardenable in CI, this directory
should be replaced with a runtime clone of `FPGA-Research/fabulous-tiles` and
`FPGA-Research/fabulous-fabrics` and the synthetic fabric removed.
