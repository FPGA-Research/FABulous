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

```{note}
The Docker images are primarily designed for headless/CLI usage. While GUI applications can work with X11 forwarding, you may encounter display-related issues depending on your host configuration. If you need reliable GUI support, we recommend using the [Nix-based setup](nix-install) instead, which provides a more seamless experience with native display integration.
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

## Building the Docker Image Locally

If you prefer to build the Docker image yourself (e.g., for development or customization), you can use the Nix-based build:

### Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled
- Docker

### Building

From the FABulous repository root:

```bash
nix-build nix/docker-image.nix
docker load < result
```

This creates a `fabulous:latest` image locally.

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
