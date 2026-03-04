FROM ubuntu:24.04

# Install minimal dependencies and set up non-root user (UID 1000)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates xz-utils git sudo && \
    rm -rf /var/lib/apt/lists/* && \
    userdel -r ubuntu 2>/dev/null || true && \
    useradd -m -s /bin/bash -u 1000 nixuser && \
    echo 'nixuser ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/nixuser && \
    chmod 0440 /etc/sudoers.d/nixuser && \
    mkdir -p /nix && chown -R nixuser:nixuser /nix

# Install Nix as nixuser and configure for single-user mode with flakes
RUN su - nixuser -c 'curl -L https://nixos.org/nix/install | sh -s -- --no-daemon' && \
    mkdir -p /home/nixuser/.config/nix && \
    { echo 'experimental-features = nix-command flakes'; \
    echo 'cores = 0'; \
    echo 'extra-substituters = https://nix-cache.fossi-foundation.org'; \
    echo 'extra-trusted-public-keys = nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs='; \
    echo 'build-users-group ='; \
    } > /home/nixuser/.config/nix/nix.conf && \
    chown -R nixuser:nixuser /home/nixuser/.config

# Copy project files for Nix build
WORKDIR /build
COPY --chown=nixuser:nixuser flake.nix flake.lock ./
COPY --chown=nixuser:nixuser nix/ ./nix/
COPY --chown=nixuser:nixuser pyproject.toml uv.lock ./
COPY --chown=nixuser:nixuser fabulous/ ./fabulous/

# Build dev shell profile as nixuser and clean up to reduce image size
USER nixuser
ENV PATH="/home/nixuser/.nix-profile/bin:$PATH"
RUN nix develop --profile /nix/var/nix/profiles/devshell --command true && \
    nix store gc && \
    nix store optimise

# Switch back to root for system-level setup
USER root

# Set up workspace, runtime dir, and devshell profile script
RUN mkdir -p /workspaces /run/user/1000 && \
    chown nixuser:nixuser /workspaces /run/user/1000 && \
    chmod 700 /run/user/1000 && \
    { echo '#!/bin/bash'; \
    echo 'DEVSHELL_DIR=${DEVSHELL_DIR:-$(find /nix/store -maxdepth 1 -type d -name "*-devshell-dir" 2>/dev/null | head -1)}'; \
    echo '[ -n "$DEVSHELL_DIR" ] && [ -f "$DEVSHELL_DIR/env.bash" ] && source "$DEVSHELL_DIR/env.bash"'; \
    echo 'export PATH="/nix/var/nix/profiles/devshell/bin:/home/nixuser/.nix-profile/bin:$PATH"'; \
    } > /etc/profile.d/devshell.sh && \
    chmod +x /etc/profile.d/devshell.sh && \
    echo 'source /etc/profile.d/devshell.sh' >> /home/nixuser/.bashrc && \
    echo 'source /etc/profile.d/devshell.sh' >> /etc/bash.bashrc && \
    chown nixuser:nixuser /home/nixuser/.bashrc

# Fix GPG "invalid signature" errors when devcontainer features run apt-get update
# in Codespaces overlay builds. The base image enables gzip indexes (docker-gzip-indexes)
# which causes file size mismatches across overlay2 layers during GPG verification.
RUN rm -f /etc/apt/apt.conf.d/docker-gzip-indexes && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update

# Initialize git repo in workspace as nixuser
USER nixuser
RUN cd /workspaces && \
    git init && \
    git config user.email "devcontainer@fabulous.local" && \
    git config user.name "Dev Container"

# Set environment variables
ENV BASH_ENV=/etc/profile.d/devshell.sh \
    XDG_RUNTIME_DIR=/run/user/1000 \
    QT_X11_NO_MITSHM=1 \
    QT_QPA_PLATFORM=offscreen \
    REPO_ROOT=/workspaces \
    PRJ_ROOT=/workspaces \
    PATH="/nix/var/nix/profiles/devshell/bin:/home/nixuser/.nix-profile/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

WORKDIR /workspaces
CMD ["/bin/bash"]
