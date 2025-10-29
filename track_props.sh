#!/bin/bash

# NBA Prop Tracker Launcher
# Simple script to run the prop tracker with virtual environment

echo "🏀 Starting NBA Prop Tracker..."
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please create one first:"
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if output.txt exists
if [ ! -f "output.txt" ]; then
    echo "❌ output.txt not found. Please make sure you have props to track."
    exit 1
fi

# Run the tracker
echo "🚀 Launching prop tracker..."
echo "   Press Ctrl+C to stop"
echo ""

python -m utility.prop_tracker "$@"
