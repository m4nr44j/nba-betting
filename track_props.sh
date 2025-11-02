#!/bin/bash

echo "🏀 Starting NBA Prop Tracker..."
echo ""

if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please create one first:"
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

source .venv/bin/activate

if [ ! -f "output.txt" ]; then
    echo "❌ output.txt not found. Please make sure you have props to track."
    exit 1
fi

echo "🚀 Launching prop tracker..."
echo "   Press Ctrl+C to stop"
echo ""

python -m utility.prop_tracker "$@"
