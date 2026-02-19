FROM ubuntu:24.04

# Install minimal dependencies and set up Nix user in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates xz-utils git sudo && \
    useradd -m -s /bin/bash nixuser && \
    mkdir -p /nix && chown -R nixuser:nixuser /nix

# Install Nix as nixuser and configure for root
RUN su - nixuser -c 'curl -L https://nixos.org/nix/install | sh -s -- --no-daemon' && \
    mkdir -p /root/.nix-profile /root/.config/nix && \
    ln -s /nix/var/nix/profiles/per-user/nixuser/profile /root/.nix-profile && \
    chown -R root:root /nix

# Configure Nix with flakes and binary caches
RUN echo 'experimental-features = nix-command flakes' > /root/.config/nix/nix.conf && \
    echo 'extra-substituters = https://nix-cache.fossi-foundation.org' >> /root/.config/nix/nix.conf && \
    echo 'extra-trusted-public-keys = nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs=' >> /root/.config/nix/nix.conf && \
    echo 'build-users-group =' >> /root/.config/nix/nix.conf

# Copy project files for Nix build
WORKDIR /build
COPY flake.nix flake.lock ./
COPY nix/ ./nix/
COPY pyproject.toml uv.lock ./
COPY FABulous/ ./FABulous/

# Build dev shell profile and clean up in single layer to reduce image size
RUN export PATH="/home/nixuser/.nix-profile/bin:$PATH" && \
    . /home/nixuser/.nix-profile/etc/profile.d/nix.sh && \
    nix develop --profile /nix/var/nix/profiles/devshell --command true && \
    nix store gc && \
    nix store optimise

# Set up workspace with dummy git repo and configure environment
RUN DEVSHELL_DIR=$(find /nix/store -maxdepth 1 -type d -name '*-devshell-dir' | head -1) && \
    mkdir -p /workspaces /run/user/0 && \
    chmod 700 /run/user/0 && \
    cd /workspaces && \
    git init && \
    git config user.email "devcontainer@fabulous.local" && \
    git config user.name "Dev Container" && \
    echo '#!/bin/bash' > /etc/profile.d/devshell.sh && \
    echo 'DEVSHELL_DIR=${DEVSHELL_DIR:-$(find /nix/store -maxdepth 1 -type d -name "*-devshell-dir" 2>/dev/null | head -1)}' >> /etc/profile.d/devshell.sh && \
    echo '[ -n "$DEVSHELL_DIR" ] && [ -f "$DEVSHELL_DIR/env.bash" ] && source "$DEVSHELL_DIR/env.bash"' >> /etc/profile.d/devshell.sh && \
    echo 'export PATH="/nix/var/nix/profiles/devshell/bin:/home/nixuser/.nix-profile/bin:$PATH"' >> /etc/profile.d/devshell.sh && \
    chmod +x /etc/profile.d/devshell.sh && \
    echo 'source /etc/profile.d/devshell.sh' >> /root/.bashrc && \
    echo 'source /etc/profile.d/devshell.sh' >> /etc/bash.bashrc

# Ensure non-interactive bash loads devshell environment
ENV BASH_ENV=/etc/profile.d/devshell.sh

# Set environment variables
ENV XDG_RUNTIME_DIR=/run/user/0 \
    QT_X11_NO_MITSHM=1 \
    QT_QPA_PLATFORM=offscreen \
    REPO_ROOT=/workspaces \
    PRJ_ROOT=/workspaces \
    PATH="/nix/var/nix/profiles/devshell/bin:/home/nixuser/.nix-profile/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

WORKDIR /workspaces
CMD ["/bin/bash"]
