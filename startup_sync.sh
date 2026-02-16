#!/bin/bash
# startup_sync.sh - Run Google Docs sync on WSL startup

# === CONFIGURATION (CHANGE THESE IF NEEDED) ===
CONTAINER_NAME="habit-db"
POSTGRES_USER="postgres"

PROJECT_DIR="/home/yume_ayasaki/projects/habit"
LOG_FILE="$PROJECT_DIR/logs/sync_startup_$(date +%Y%m%d_%H%M%S).log"

echo "=== WSL Startup Sync Started at $(date) ===" | tee -a "$LOG_FILE"

# 1. Wait for Docker daemon to be fully ready
echo "Waiting for Docker daemon..." | tee -a "$LOG_FILE"
timeout=45
while [ $timeout -gt 0 ] && ! docker info >/dev/null 2>&1; do
    sleep 1
    ((timeout--))
done
if [ $timeout -eq 0 ]; then
    echo "ERROR: Docker failed to start within 45s!" | tee -a "$LOG_FILE"
    exit 1
fi
echo "Docker daemon is ready." | tee -a "$LOG_FILE"

# 2. Wait for the Postgres container to be running
echo "Waiting for container '$CONTAINER_NAME' to start..." | tee -a "$LOG_FILE"
timeout=60
while [ $timeout -gt 0 ]; do
    if docker ps -q -f "name=^${CONTAINER_NAME}$" | grep -q .; then
        echo "Container '$CONTAINER_NAME' is running." | tee -a "$LOG_FILE"
        break
    fi
    sleep 2
    ((timeout-=2))
done
if [ $timeout -le 0 ]; then
    echo "ERROR: Container '$CONTAINER_NAME' did not start within 60s!" | tee -a "$LOG_FILE"
    exit 1
fi

# 3. Wait for Postgres to actually accept connections (the real fix)
echo "Waiting for Postgres to be ready (pg_isready)..." | tee -a "$LOG_FILE"
timeout=90   # generous for cold boot
while [ $timeout -gt 0 ]; do
    if docker exec "$CONTAINER_NAME" pg_isready -U "$POSTGRES_USER" -q 2>/dev/null; then
        echo "Postgres is ready to accept connections!" | tee -a "$LOG_FILE"
        break
    fi
    sleep 3
    ((timeout-=3))
done
if [ $timeout -le 0 ]; then
    echo "WARNING: Postgres not ready after 90s – proceeding anyway (may still fail)" | tee -a "$LOG_FILE"
fi

# === Now safe to run your code ===
cd "$PROJECT_DIR" || { echo "Failed to cd to project dir" | tee -a "$LOG_FILE"; exit 1; }

# Virtual env
if [ -d ".venv" ]; then
    echo "Activating virtual environment..." | tee -a "$LOG_FILE"
    source ".venv/bin/activate"
else
    echo "No virtual environment found, proceeding without activation." | tee -a "$LOG_FILE"
fi

echo "Running google_docs.py..." | tee -a "$LOG_FILE"
python google_docs.py 2>&1 | tee -a "$LOG_FILE"

echo "=== Sync Completed at $(date) ===" | tee -a "$LOG_FILE"