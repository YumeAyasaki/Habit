#!/bin/bash
# activate_env.sh - Activate Python virtual environment

# Get the project directory (parent of scripts directory, or from argument)
if [ -n "$1" ]; then
    PROJECT_DIR="$1"
else
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
fi

# Virtual env
if [ -d "$PROJECT_DIR/.venv" ]; then
    echo "Activating virtual environment at $PROJECT_DIR/.venv..." >&2
    source "$PROJECT_DIR/.venv/bin/activate"
else
    echo "No virtual environment found at $PROJECT_DIR/.venv, proceeding without activation." >&2
fi
