#!/usr/bin/env bash
set -euo pipefail

# MongoDB Restore Script
# Copies a local mongodump backup into the Docker container and restores it
# with mongorestore. Can target the local container or any remote MongoDB server.
# Password: MONGO_BACKUP_PASSWORD env var takes precedence over --password flag.

CONTAINER="mongodb"
HOST="server.home"
PORT="27017"
USERNAME="root"
PASSWORD=""
AUTH_SOURCE="admin"
SOURCE=""
DATABASES=""

usage() {
  cat <<EOF
Usage: $(basename "$0") --source BACKUP_DIR [OPTIONS]

Restore a MongoDB backup created by backup_mongo.sh. Can restore to the local
Docker container or to another server via --host/--port.

Options:
  --source DIR            Local backup directory to restore (required)
  --databases DB1,DB2     Comma-separated list of databases to restore (default: all in dump)
  --username USER         Target MongoDB username (default: root)
  --password PASS         Target MongoDB password (env MONGO_BACKUP_PASSWORD takes precedence)
  --auth-source DB        Target auth database (default: admin)
  --host HOST             Target MongoDB host (default: server.home)
  --port PORT             Target MongoDB port (default: 27017)
  --container NAME        Local Docker container used to run mongorestore (default: mongodb)
  -h, --help              Show this help message and exit
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)      SOURCE="$2"; shift 2 ;;
    --databases)   DATABASES="$2"; shift 2 ;;
    --username)    USERNAME="$2"; shift 2 ;;
    --password)    PASSWORD="$2"; shift 2 ;;
    --auth-source) AUTH_SOURCE="$2"; shift 2 ;;
    --host)        HOST="$2"; shift 2 ;;
    --port)        PORT="$2"; shift 2 ;;
    --container)   CONTAINER="$2"; shift 2 ;;
    -h|--help)     usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

if [[ -z "$SOURCE" ]]; then
  echo "Error: --source is required." >&2
  usage
fi

if [[ ! -d "$SOURCE" ]]; then
  echo "Error: Source directory '$SOURCE' does not exist or is not a directory." >&2
  exit 1
fi

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

# Copy backup into container
CONTAINER_RESTORE_PATH="/tmp/mongo_restore"
docker exec "$CONTAINER" rm -rf "$CONTAINER_RESTORE_PATH"
docker exec "$CONTAINER" mkdir -p "$CONTAINER_RESTORE_PATH"
echo "Copying backup to container..."
docker cp "$SOURCE/." "${CONTAINER}:${CONTAINER_RESTORE_PATH}/"

# Build mongorestore args
RESTORE_ARGS=(
  --host "$HOST" --port "$PORT"
  -u "$USERNAME" -p "$PASSWORD"
  --authenticationDatabase "$AUTH_SOURCE"
  --dir "$CONTAINER_RESTORE_PATH"
)

if [[ -n "$DATABASES" ]]; then
  IFS=',' read -ra DB_LIST <<< "$DATABASES"
  for db in "${DB_LIST[@]}"; do
    RESTORE_ARGS+=(--nsInclude "$db.*")
  done
  echo "Restoring databases: $DATABASES"
else
  echo "Restoring all databases..."
fi

# Run mongorestore inside container
echo "Running mongorestore against ${HOST}:${PORT}..."
docker exec -t "$CONTAINER" mongorestore "${RESTORE_ARGS[@]}" 2>&1

# Clean up container temp path
docker exec "$CONTAINER" rm -rf "$CONTAINER_RESTORE_PATH"

echo ""
echo "Restore complete."
