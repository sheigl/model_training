#!/usr/bin/env bash
set -euo pipefail

# MongoDB Backup Script
# Runs mongodump inside the Docker container and copies the dump to the host.
# Password: MONGO_BACKUP_PASSWORD env var takes precedence over --password flag.

CONTAINER="mongodb"
HOST="server.home"
PORT="27017"
USERNAME="root"
PASSWORD=""
AUTH_SOURCE="admin"
OUTPUT_DIR="$HOME/mongo_backups"
DATABASES=""
LIST_ONLY=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Backup MongoDB databases running in Docker.

Options:
  --output-dir DIR        Base output directory (default: ~/mongo_backups/)
  --databases DB1,DB2     Comma-separated list of databases to back up (default: all)
  --list-databases        List available databases and exit
  --username USER         MongoDB username (default: root)
  --password PASS         MongoDB password (env MONGO_BACKUP_PASSWORD takes precedence)
  --auth-source DB        Auth database (default: admin)
  --host HOST             MongoDB host (default: server.home)
  --port PORT             MongoDB port (default: 27017)
  --container NAME        Docker container name (default: mongodb)
  -h, --help              Show this help message and exit
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)   OUTPUT_DIR="$2"; shift 2 ;;
    --databases)    DATABASES="$2"; shift 2 ;;
    --list-databases) LIST_ONLY=true; shift ;;
    --username)     USERNAME="$2"; shift 2 ;;
    --password)     PASSWORD="$2"; shift 2 ;;
    --auth-source)  AUTH_SOURCE="$2"; shift 2 ;;
    --host)         HOST="$2"; shift 2 ;;
    --port)         PORT="$2"; shift 2 ;;
    --container)    CONTAINER="$2"; shift 2 ;;
    -h|--help)      usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

# Password: env var takes precedence
PASSWORD="${MONGO_BACKUP_PASSWORD:-$PASSWORD}"
if [[ -z "$PASSWORD" ]]; then
  echo "Error: No password provided. Set MONGO_BACKUP_PASSWORD or use --password." >&2
  exit 1
fi

# Verify docker and container
if ! command -v docker &>/dev/null; then
  echo "Error: docker is not installed or not in PATH." >&2
  exit 1
fi

if ! docker inspect "$CONTAINER" &>/dev/null; then
  echo "Error: Docker container '$CONTAINER' not found." >&2
  exit 1
fi

# Helper to run mongodump flags
mongodump_cmd_base=(
  docker exec "$CONTAINER" mongodump
  --host "$HOST" --port "$PORT"
  -u "$USERNAME" -p "$PASSWORD"
  --authenticationDatabase "$AUTH_SOURCE"
)

# List databases and exit
if [[ "$LIST_ONLY" == true ]]; then
  echo "Databases on ${HOST}:${PORT}:"
  docker exec -t "$CONTAINER" mongosh \
    --host "$HOST" --port "$PORT" \
    -u "$USERNAME" -p "$PASSWORD" --authenticationDatabase "$AUTH_SOURCE" \
    --quiet --eval 'db.adminCommand("listDatabases").databases.forEach(d => print(`${d.name}\t${(d.sizeOnDisk/1024/1024).toFixed(2)} MB`))'
  exit 0
fi

# Build mongodump args
DUMP_ARGS=()
if [[ -n "$DATABASES" ]]; then
  IFS=',' read -ra DB_LIST <<< "$DATABASES"
  for db in "${DB_LIST[@]}"; do
    DUMP_ARGS+=(--db "$db")
  done
  echo "Backing up databases: $DATABASES"
else
  echo "Backing up all databases..."
fi

# Create timestamped output directory
TIMESTAMP=$(date +"%Y-%m-%d_%H%M")
DEST="${OUTPUT_DIR}/${TIMESTAMP}"
mkdir -p "$DEST"

# Run mongodump inside container
CONTAINER_DUMP_PATH="/tmp/mongo_dump"
echo "Running mongodump..."
"${mongodump_cmd_base[@]}" --out "$CONTAINER_DUMP_PATH" "${DUMP_ARGS[@]}" 2>&1

# Copy dump from container to host
echo "Copying dump to ${DEST}/"
docker cp "${CONTAINER}:${CONTAINER_DUMP_PATH}/." "$DEST/"

# Clean up container temp path
docker exec "$CONTAINER" rm -rf "$CONTAINER_DUMP_PATH"

# Summary
echo ""
echo "Backup complete: ${DEST}"
du -sh "$DEST"/* 2>/dev/null || true
