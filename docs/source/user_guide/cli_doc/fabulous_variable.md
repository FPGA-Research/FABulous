(fabulous-variables)=

# FABulous Configuration Variables

FABulous can use environment variables to configure options, paths and projects. We distinguish between two types of environment variables: **global** and **project specific** environment variables.

- **Global environment variables** are used to configure FABulous itself. They always start with `FAB_`.
- **Project specific environment variables** are used to configure a specific FABulous project. They always start with `FAB_PROJ_`.

All environment variables can be set in the shell before running FABulous or can be set via `.env` files.

## `.env` File Locations

| Scope | Location | How to use |
|-------|----------|------------|
| User global | `~/.config/FABulous/.env` | Created automatically or manually |
| Global (explicit) | Any path | Pass via `--globalDotEnv` CLI argument |
| Project (auto-detected) | `<project_dir>/.FABulous/.env` | Placed inside your project |
| Project (explicit) | Any path | Pass via `--projectDotEnv` CLI argument |

:::{note}
Environment variables set in the **shell** always have the **highest priority**, followed by project-specific `.env` files, then global `.env` files.
:::

(pdk-resolution-logic)=
## PDK Resolution Logic

FABulous uses three environment variables to locate and manage a Process Design Kit (PDK) for back-end GDS generation.

| Variable | Purpose |
|----------|---------|
| `FAB_PDK` | Name of the PDK (e.g. `ihp-sg13g2`) |
| `FAB_PDK_ROOT` | File-system path to the PDK installation directory |
| `FAB_PDK_HASH` | Version hash identifying a specific PDK snapshot |

### Default value of `FAB_PDK`

When a new project is created with `create_project`, `FAB_PDK` is set to `ihp-sg13g2` in the project `.env` file by default. This value can be overridden afterward.

### Resolution at startup

When FABulous loads its settings, the following rules determine how the PDK is resolved. For ciel-supported PDKs, FABulous handles installation and activation automatically, so there is no need to manually run `ciel enable`.

1. **Neither `FAB_PDK` nor `FAB_PDK_ROOT` is set.** A warning is logged and GDS features are unavailable.
2. **`FAB_PDK_ROOT` is set but `FAB_PDK` is missing.** An error is raised asking the user to set `FAB_PDK`.
3. **`FAB_PDK` is set without `FAB_PDK_ROOT`, and the PDK belongs to a ciel-supported family.** `FAB_PDK_ROOT` is automatically resolved from the ciel home directory and the PDK is installed and activated via ciel.
4. **`FAB_PDK` is set without `FAB_PDK_ROOT`, and the PDK is not ciel-supported.** An error is raised asking the user to set `FAB_PDK_ROOT` manually.
5. **Both are set, but the PDK is not a ciel family.** FABulous assumes a custom PDK with manual setup. The path must exist on disk.
6. **Both are set and the PDK is a ciel family.** The recommended `FAB_PDK_HASH` is resolved from librelane. If the user did not provide `FAB_PDK_HASH`, it is filled in automatically; if the user-provided value differs from the recommended one, a mismatch warning is logged. The PDK is then installed and activated via ciel.

```{include} /generated_doc/fabulous_variable.md
```
