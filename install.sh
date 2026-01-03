#!/bin/sh
# Porterminal installer for macOS/Linux
# Usage: curl -LsSf https://raw.githubusercontent.com/lyehe/porterminal/main/install.sh | sh

set -e

echo ""
echo "    ____             __                      _             __"
echo "   / __ \\____  _____/ /____  _________ ___  (_)___  ____ _/ /"
echo "  / /_/ / __ \\/ ___/ __/ _ \\/ ___/ __  __ \\/ / __ \\/ __  / / "
echo " / ____/ /_/ / /  / /_/  __/ /  / / / / / / / / / / /_/ / /  "
echo "/_/    \\____/_/   \\__/\\___/_/  /_/ /_/ /_/_/_/ /_/\\__,_/_/   "
echo "                                                      >_"
echo ""

# Check if uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo "[1/2] Installing uv..."

    # Install uv using their official installer
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        echo "Failed to install uv"
        echo "Please install uv manually: https://docs.astral.sh/uv/"
        exit 1
    fi

    # Source the env to get uv in PATH
    if [ -f "$HOME/.local/bin/env" ]; then
        . "$HOME/.local/bin/env"
    elif [ -f "$HOME/.cargo/env" ]; then
        . "$HOME/.cargo/env"
    fi

    # Also add to PATH directly for this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    echo "[OK] uv installed"
else
    echo "[1/2] uv found"
fi

echo "[2/2] Installing Porterminal..."

# Install ptn using uv tool
if ! uv tool install --force ptn; then
    echo "Failed to install Porterminal"
    exit 1
fi

echo ""
echo "[OK] Porterminal installed!"
echo ""
echo "Run:"
echo "  ptn"
echo ""
echo "Or run without installing:"
echo "  uvx ptn"
echo ""
