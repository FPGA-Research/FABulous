(fabulous-variables)=
# FABulous Configuration Variables

This is an auto-generated reference of all FABulous configuration variables.

## Environment Variables

FABulous settings can be configured via environment variables with the `FAB_` prefix. These can be set in your shell or in a `.env` file in your project's `.FABulous` directory.


### Tool Paths

| Variable | Environment Variable | Type | Default | Description |
|----------|---------------------|------|---------|-------------|
| `yosys_path` | `FAB_YOSYS_PATH` | Path | yosys | - |
| `nextpnr_path` | `FAB_NEXTPNR_PATH` | Path | nextpnr-generic | - |
| `iverilog_path` | `FAB_IVERILOG_PATH` | Path | iverilog | - |
| `vvp_path` | `FAB_VVP_PATH` | Path | vvp | - |
| `ghdl_path` | `FAB_GHDL_PATH` | Path | ghdl | - |
| `openroad_path` | `FAB_OPENROAD_PATH` | Path | openroad | - |
| `klayout_path` | `FAB_KLAYOUT_PATH` | Path | klayout | - |
| `fabulator_root` | `FAB_FABULATOR_ROOT` | Path | None | - |
| `oss_cad_suite` | `FAB_OSS_CAD_SUITE` | Path | None | - |



### Project Settings

| Variable | Environment Variable | Type | Default | Description |
|----------|---------------------|------|---------|-------------|
| `proj_dir` | `FAB_PROJ_DIR` | Path | - | - |
| `proj_lang` | `FAB_PROJ_LANG` | HDLType | - | - |
| `models_pack` | `FAB_MODELS_PACK` | Path | None | - |
| `proj_version` | `FAB_PROJ_VERSION` | Version | - | - |
| `proj_version_created` | `FAB_PROJ_VERSION_CREATED` | Version | 0.0.1 | - |
| `user_config_dir` | `FAB_USER_CONFIG_DIR` | Path | - | - |



### GDS Settings

| Variable | Environment Variable | Type | Default | Description |
|----------|---------------------|------|---------|-------------|
| `pdk_root` | `FAB_PDK_ROOT` | Path | None | - |
| `pdk` | `FAB_PDK` | str | None | - |
| `fabric_die_area` | `FAB_FABRIC_DIE_AREA` | tuple | - | - |
| `switch_matrix_debug_signal` | `FAB_SWITCH_MATRIX_DEBUG_SIGNAL` | bool | False | - |



### CLI Settings

| Variable | Environment Variable | Type | Default | Description |
|----------|---------------------|------|---------|-------------|
| `editor` | `FAB_EDITOR` | str | None | - |
| `verbose` | `FAB_VERBOSE` | int | 0 | - |
| `debug` | `FAB_DEBUG` | bool | False | - |



## Interactive CLI Settables

These variables can be set and get interactively in the FABulous CLI using the `set` and `get` commands.

**Usage:**
```bash
FABulous> set <variable> <value>
FABulous> get <variable>
```

| Variable | Type | Description |
|----------|------|-------------|
| `projectDir` | Path | The directory of the project |
| `csvFile` | Path | The fabric CSV definition file |
| `verbose` | bool | Enable verbose output |
| `force` | bool | Force execution without confirmation |
