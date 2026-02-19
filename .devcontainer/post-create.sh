#!/bin/bash
# This script runs after the container is created
# It handles environment-specific setup

# Check if running in Codespaces
if [ -z "$CODESPACES" ]; then
    # Local development environment
    echo "Local development environment detected"
    
    # Setup X11 forwarding for local GUI applications
    if [ -n "$DISPLAY" ]; then
        echo "Setting up X11 forwarding..."
        export DISPLAY="$DISPLAY"
        
        # Create .Xauthority if it doesn't exist
        if [ ! -f "$HOME/.Xauthority" ]; then
            touch "$HOME/.Xauthority"
            chmod 600 "$HOME/.Xauthority"
        fi
        
        echo "X11 display: $DISPLAY"
    else
        echo "Warning: DISPLAY variable not set. GUI applications may not work."
    fi
else
    # GitHub Codespaces environment
    echo "GitHub Codespaces environment detected"
    # Codespaces uses web-based desktop-lite interface, no X11 setup needed
fi

echo "FABulous environment ready"
