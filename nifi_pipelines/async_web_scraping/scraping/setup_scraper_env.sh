#!/bin/bash

# Exit on error
set -e

# Define project directory
PROJECT_DIR="/opt/web_scraping"
PYTHON_VERSION="3.11"

echo "=== Step 1: Install Python $PYTHON_VERSION and dependencies ==="
sudo apt update
sudo apt install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv snapd curl

echo "=== Step 2: Install uv ==="
sudo snap install uv --classic

echo "=== Step 3: Create project directory and move there ==="
sudo mkdir -p "$PROJECT_DIR"
sudo chown "$USER":"$USER" "$PROJECT_DIR"
cd "$PROJECT_DIR"

echo "=== Step 4: Create virtual environment with uv ==="
uv venv --python ${PYTHON_VERSION}

echo "=== Step 5: Activate venv and install dependencies ==="
source .venv/bin/activate
uv pip install browser-use

echo "=== Step 6: Install Playwright ==="
uv run playwright install

echo "=== Done! ==="
echo "To activate your virtual environment in future, run:"
echo "  source $PROJECT_DIR/.venv/bin/activate"
echo
echo "To run your scraper with sudo, use:"
echo "  sudo $PROJECT_DIR/.venv/bin/python $PROJECT_DIR/scraping_v1.py 'https://example.com'"
