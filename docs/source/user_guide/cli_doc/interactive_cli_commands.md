(interactive-cli-commands-reference)=
# Interactive CLI Commands Reference

This is an auto-generated reference of all FABulous CLI commands available in interactive mode.


## Setup


### `install_FABulator`

Download and install the latest version of FABulator.

Sets the the FABULATOR_ROOT environment variable in the .env file.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `destination_folder` | Path | No | - | Destination folder for the installation |







### `install_oss_cad_suite`

Download and extract the latest OSS CAD suite.

The installation will set the `FAB_OSS_CAD_SUITE` environment variable
in the `.env` file.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `destination_folder` | Path | No | - | Destination folder for the installation |







### `load_fabric`

Load 'fabric.csv' file and generate an internal representation of the fabric.

Parse input arguments and set a few internal variables to assist fabric
generation.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | Path | No | - | Path to the target file |








## Fabric Flow


### `gen_all_tile`

Generate all tiles by calling `do_gen_tile`.






### `gen_all_tile_macros`

Generate GDSII files for all tiles in the fabric.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `parallel` | str | No | False | Generate tile macros in parallel |







### `gen_bitStream_spec`

Generate bitstream specification of the fabric.

By calling `genBitStreamSpec` and saving the specification to a binary and CSV
file.

Also logs the paths of the output files.






### `gen_config_mem`

Generate configuration memory of the given tile.

Parsing input arguments and calling `genConfigMem`.

Logs generation processes for each specified tile.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `tiles` | str | No | - | A list of tile |







### `gen_fabric`

Generate fabric based on the loaded fabric.

Calling `gen_all_tile` and `genFabric`.

Logs start and completion of fabric generation process.






### `gen_fabric_macro`

Generate GDSII files for the entire fabric.






### `gen_geometry`

Generate geometry of fabric for FABulator.

Checking if fabric is loaded, and calling 'genGeometry' and passing on padding
value. Default padding is '8'.

Also logs geometry generation, the used padding value and any warning about
faulty padding arguments, as well as errors if the fabric is not loaded or the
padding is not within the valid range of 4 to 32.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `padding` | int | No | 8 | Padding value for geometry generation |







### `gen_io_fabric`

Generate I/O BELs for the entire fabric.

This command generates Input/Output Basic Elements of Logic (BELs) for all
applicable tiles in the fabric, providing external connectivity
across the entire FPGA design.






### `gen_io_tiles`

Generate I/O BELs for specified tiles.

This command generates Input/Output Basic Elements of Logic (BELs) for the
specified tiles, enabling external connectivity for the FPGA fabric.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `tiles` | str | No | - | A list of tile |







### `gen_model_npnr`

Generate Nextpnr model of fabric.

By parsing various required files for place and route such as `pips.txt`,
`bel.txt`, `bel.v2.txt` and `template.pcf`. Output files are written to the
directory specified by `metaDataDir` within `projectDir`.

Logs output file directories.






### `gen_switch_matrix`

Generate switch matrix of given tile.

Parsing input arguments and calling `genSwitchMatrix`.

Also logs generation process for each specified tile.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `tiles` | str | No | - | A list of tile |







### `gen_tile`

Generate given tile with switch matrix and configuration memory.

Parsing input arguments, call functions such as `genSwitchMatrix` and
`genConfigMem`. Handle both regular tiles and super tiles with sub-tiles.

Also logs generation process for each specified tile and sub-tile.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `tiles` | str | No | - | A list of tile |







### `gen_tile_macro`

Generate GDSII files for a specific tile.

This command generates GDSII files for the specified tile, allowing for
the physical representation of the tile to be created.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `tile` | str | Yes | - | A tile |







### `gen_top_wrapper`

Generate top wrapper of the fabric by calling `genTopWrapper`.






### `run_FABulous_eFPGA_macro`

Run the full FABulous eFPGA macro generation flow.






### `run_FABulous_fabric`

Generate the fabric based on the CSV file.

Create bitstream specification of the fabric, top wrapper of the fabric, Nextpnr
model of the fabric and geometry information of the fabric.







## User Design Flow


### `gen_bitStream_binary`

Generate bitstream of a given design.

Using FASM file and pre-generated bitstream specification file
`bitStreamSpec.bin`. Requires bitstream specification before use by running
`gen_bitStream_spec` and place and route file generated by running
`place_and_route`.

Also logs output file directory, Bitstream generation error and file not found
error.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | Path | Yes | - | Path to the target file |







### `gen_user_design_wrapper`

Generate a user design wrapper for the specified user design.

This command creates a wrapper module that interfaces the user design
with the FPGA fabric, handling signal connections and naming conventions.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `user_design` | Path | Yes | - | Path to user design file |







### `place_and_route`

Run place and route with Nextpnr for a given JSON file.

Generated by Yosys, which requires a Nextpnr model and JSON file first,
generated by `synthesis`.

Also logs place and route error, file not found error and type error.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | Path | Yes | - | Path to the target file |







### `run_FABulous_bitstream`

Run FABulous to generate bitstream on a given design.

Does this by calling synthesis, place and route, bitstream generation functions.
Requires Verilog file specified by <top_module_file>.

Also logs usage error and file not found error.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | Path | Yes | - | Path to the target file |







### `run_simulation`

Simulate given FPGA design using Icarus Verilog (iverilog).

If <fst> is specified, waveform files in FST format will generate, <vcd> with
generate VCD format. The bitstream_file argument should be a binary file
generated by 'gen_bitStream_binary'. Verilog files from 'Tile' and 'Fabric'
directories are copied to the temporary directory 'tmp', 'tmp' is deleted on
simulation end.

Also logs simulation error and file not found error and value error.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `format` | str | No | fst | Output format of the simulation |








## Helper


### `print_bel`

Print a Bel object to the console.






### `print_tile`

Print a tile object to the console.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `tile` | str | Yes | - | A tile |








## GUI


### `start_FABulator`

Start FABulator if an installation can be found.

If no installation can be found, a warning is produced.







## Script


### `run_script`

Execute script.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | Path | Yes | - | Path to the target file |







### `run_tcl`

Execute TCL script relative to the project directory.

Specified by <tcl_scripts>. Use the 'tk' module to create TCL commands.

Also logs usage errors and file not found errors.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | Path | Yes | - | Path to the target file |








## Tools


### `generate_custom_tile_config`

Generate a custom tile configuration for a given tile folder.

Or path to bel folder. A tile `.csv` file and a switch matrix `.list` file will
be generated.

The provided path may contain bel files, which will be included in the generated
tile .csv file as well as the generated switch matrix .list file.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `tile_path` | Path | Yes | - | Path to the target tile directory |







### `start_klayout_gui`

Start OpenROAD GUI if an installation can be found.

If no installation can be found, a warning is produced.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | str | No | None | file to open |
| `tile` | str | No | None | launch GUI to view a specific tile |







### `start_openroad_gui`

Start OpenROAD GUI if an installation can be found.

If no installation can be found, a warning is produced.


**Arguments:**

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | str | No | None | file to open |
| `tile` | str | No | None | launch GUI to view a specific tile |








## Other


### `exit`

Exit the FABulous shell and log info message.






### `q`

Exit the FABulous shell and log info message.






### `quit`

Exit the FABulous shell and log info message.






### `synthesis`

Run synthesis on the specified design.





