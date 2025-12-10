(docker-install)=
# `docker` based setup

We provide Docker images for FABulous that include all necessary tools and dependencies pre-installed. This is the recommended approach for users who want an all-in-one, fully encapsulated environment without having to install any dependencies on their host system (assume you have `docker` installed).

## Pre-built Docker Images

We provide two Docker images:

| Image | Tag | Description |
|-------|-----|-------------|
| Release | `latest` | For end users - FABulous is pre-installed and ready to use |
| Development | `dev` | For developers - uses editable install, changes to mounted source code are reflected immediately |

### Release Image (Recommended for Users)

```bash
docker pull ghcr.io/fpga-research/fabulous:latest
```

### Development Image (For Contributors)

```bash
docker pull ghcr.io/fpga-research/fabulous:dev
```

## Running the Docker Container

### Basic Usage

To launch into the Docker container with your current directory mounted:

```bash
docker run -it -v $PWD:/workspace ghcr.io/fpga-research/fabulous:latest
```

This starts an interactive shell with your current directory mounted at `/workspace`.

### Development Usage

For FABulous development, use the `dev` image with the FABulous repository mounted:

```bash
# Clone the FABulous repository (if you haven't already)
git clone https://github.com/FPGA-Research/FABulous.git
cd FABulous

# Run the dev container
docker run -it -v $PWD:/workspace ghcr.io/fpga-research/fabulous:dev
```

The dev image uses an editable install, so any changes you make to the source code in `/workspace` are immediately reflected without rebuilding the image.

### With GUI Support (Linux)

To run GUI applications like `openroad -gui`, you need to enable X11 forwarding:

```bash
# Allow Docker to access your X11 display
xhost +local:docker

# Run the container with X11 forwarding
docker run -it \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v $PWD:/workspace \
    ghcr.io/fpga-research/fabulous:latest
```

You can then run GUI tools inside the container:

```bash
openroad -gui
```

```{note}
After you're done, you can revoke X11 access with:
`xhost -local:docker`
```

## Using Dev Containers (Local Development)

For a seamless development experience with VSCode, we provide Dev Container configurations that automatically set up the entire FABulous environment including GUI support.

### Prerequisites

- [Visual Studio Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- Docker installed and running

### Getting Started

1. Clone the FABulous repository:

```bash
git clone https://github.com/FPGA-Research/FABulous.git
cd FABulous
```

2. Open the repository in VS Code:

```bash
code .
```

3. When prompted, click "Reopen in Container" or use the command palette (F1) and select "Dev Containers: Reopen in Container" then select the `Local` setup.

4. VS Code will automatically:
   - Pull the FABulous Docker image
   - Set up X11 forwarding for GUI applications
   - Configure the Python environment
   - Install recommended extensions (Ruff, Python)

```{note}
The dev container automatically runs `xhost +local:docker` on your host machine during initialization. GUI applications should work seamlessly.
```

## Troubleshooting

### GUI applications crash with "could not connect to display"

Make sure you've allowed Docker to access X11:

```bash
xhost +local:docker
```

And that you're passing the display environment variable:

```bash
docker run -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix ...
```

### Permission denied errors

If you encounter permission issues with files created inside the container being owned by root, you may need to adjust file ownership after exiting the container:

```bash
sudo chown -R $(id -u):$(id -g) .
```

### OpenGL/GLX warnings

Warnings like `qglx_findConfig: Failed to finding matching FBConfig` are normal when running without hardware acceleration. The GUI will still work using software rendering.
