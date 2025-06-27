#!/bin/bash

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3 to run this application."
    exit 1
fi

# Create a combined main.py - copy main-integrated.py to main.py
echo "Preparing integrated main.py..."
cp main-integrated.py main.py

# Start the server using the integrated main
echo "Starting MosaicMaster & Königstiger..."
python3 main.py