#!/bin/bash

# 1. GitHub Codespaces (Keep VNC)
if [ "$CODESPACES" = "true" ]; then
    echo "☁️  Running in Codespaces."
    export DISPLAY=:1
    if ! grep -q "export DISPLAY=:1" ~/.bashrc; then
        echo "export DISPLAY=:1" >> ~/.bashrc
    fi

# 2. Local Linux (Network Host Mode)
else
    echo "🐧 Running on Local Linux (Net=Host)."
    
    # Because we use --net=host, we can see the Host's Abstract Sockets.
    # We just need to make sure DISPLAY matches your host.
    
    # 1. Kill the internal VNC to free up the port/socket if it conflicts
    pkill Xvfb 2>/dev/null || true
    rm -f /tmp/.X11-unix/X1
    
    # 2. Set the display to your host's display (usually :1 on Pop!_OS)
    # We trust the variable passed from the host now.
    if [ -z "$DISPLAY" ]; then
        export DISPLAY=:1
    fi
    
    echo "   -> Using Display: $DISPLAY"

    # 3. Disable Auth (Relies on xhost +)
    export XAUTHORITY=""
    
    # 4. Persist
    sed -i '/export DISPLAY=/d' ~/.bashrc
    sed -i '/export XAUTHORITY=/d' ~/.bashrc
    echo "export DISPLAY=$DISPLAY" >> ~/.bashrc
    echo "export XAUTHORITY=\"\"" >> ~/.bashrc
fi