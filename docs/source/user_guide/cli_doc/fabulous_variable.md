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

```{include} /generated_doc/fabulous_variable.md
```
