#!/bin/bash

# Configures the display server based on the environment:
# - Codespaces: uses the built-in VNC server on :1
# - Local Linux: switches from VNC to host X11 via socket mount

if [ "$CODESPACES" = "true" ]; then
    echo "Running in Codespaces (VNC on :1)"
    export DISPLAY=:1
else
    echo "Running on Local Linux (X11 socket mount)"

    # Kill internal VNC to avoid conflicts with host X11
    pkill Xvfb 2>/dev/null || true
    rm -f /tmp/.X11-unix/X1 2>/dev/null || true

    # Link host X11 socket from mount point
    if [ -d "/tmp/.host-X11-unix" ]; then
        ln -sf /tmp/.host-X11-unix/* /tmp/.X11-unix/ 2>/dev/null || true
    fi

    # Use the DISPLAY variable passed from the host
    export DISPLAY="${DISPLAY:-:0}"
    echo "Using display: $DISPLAY"

    # Disable auth (relies on xhost +local:docker on host)
    export XAUTHORITY=""
fi

# Persist display settings to bashrc for new terminal sessions
sed -i '/export DISPLAY=/d; /export XAUTHORITY=/d' ~/.bashrc
echo "export DISPLAY=$DISPLAY" >> ~/.bashrc
if [ "$CODESPACES" != "true" ]; then
    echo 'export XAUTHORITY=""' >> ~/.bashrc
fi
