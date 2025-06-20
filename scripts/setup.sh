#!/bin/bash

# Setup script for the content collector project

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install production dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Run database migrations
alembic upgrade head

# Print completion message
echo "Setup completed successfully. The environment is ready."