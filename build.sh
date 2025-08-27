#!/usr/bin/env bash
# exit on error so the build fails fast
set -o errexit

# Install the C compiler and other essential build tools
echo "-----> Installing system dependencies"
apt-get update && apt-get install -y build-essential

# Upgrade pip and install your Python packages
echo "-----> Installing Python dependencies"
pip install --upgrade pip
pip install -r requirements.txt