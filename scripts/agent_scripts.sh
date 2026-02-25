#!/bin/bash
# agent_scripts.sh - Run stuffs for agent...

# === CONFIGURATION (CHANGE THESE IF NEEDED) ===
CONTAINER_NAME="habit-db"
POSTGRES_USER="postgres"
# Dynamic project dir
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

echo "=== Agent Scripts Started at $(date +%Y%m%d_%H%M%S) ==="

# Get script directory
SCRIPT_DIR="$PROJECT_DIR/scripts"

# Run to ensure database
# Without logging for cleaner output
echo "Running startup_sync.sh to ensure database is ready..."
"$SCRIPT_DIR/startup_sync.sh" > /dev/null 2>&1

# Activate virtual environment
cd "$PROJECT_DIR" || { echo "Failed to cd to project dir" | tee -a "$LOG_FILE"; exit 1; }
source "./scripts/activate_env.sh" "$PROJECT_DIR"

echo "Running get_progress.py..."
python get_progress.py
