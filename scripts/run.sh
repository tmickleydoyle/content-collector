#!/bin/bash

# Activate the virtual environment
source venv/bin/activate

# Run the content collector application
python -m content_collector.cli.main "$@"