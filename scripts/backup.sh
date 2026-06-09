#!/usr/bin/env bash
# Back up the Aviation Maintenance Records Processor.
#
# Takes a *consistent* SQLite snapshot (via SQLite's online backup API, so it's
# safe while the app is writing), then archives the whole ./data folder
# (database, uploads, output, templates). Keeps the most recent N archives.
#
# Usage:   scripts/backup.sh [backup_dir]
# Cron:    0 2 * * *  cd /srv/ocrdocumentverify && scripts/backup.sh >> backup.log 2>&1
set -euo pipefail

# Resolve repo root (parent of this script's directory).
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_DIR="${1:-$ROOT_DIR/backups}"
DATA_DIR="$ROOT_DIR/data"
RETAIN="${RETAIN:-14}"            # how many archives to keep
TS="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR" "$DATA_DIR/db"

# 1. Consistent DB snapshot using the running app container's Python (the slim
#    image has no sqlite3 CLI, but it always has Python + sqlite3 module).
echo "[$(date)] Snapshotting database…"
docker compose exec -T app python -c "
import sqlite3, os
src = sqlite3.connect(os.environ['RECORDS_DB'])
dst = sqlite3.connect('/data/records_snapshot.db')
with dst:
    src.backup(dst)
src.close(); dst.close()
print('  snapshot written to data/db/records_snapshot.db')
"

# 2. Archive the entire data folder (snapshot + uploads + output + templates).
ARCHIVE="$BACKUP_DIR/maint_backup_$TS.tar.gz"
echo "[$(date)] Archiving data folder → $ARCHIVE"
tar -czf "$ARCHIVE" -C "$ROOT_DIR" data

# 3. Prune old archives, keeping the newest $RETAIN.
echo "[$(date)] Pruning to the newest $RETAIN archive(s)…"
ls -1t "$BACKUP_DIR"/maint_backup_*.tar.gz 2>/dev/null \
  | tail -n +"$((RETAIN + 1))" \
  | xargs -r rm -f

echo "[$(date)] Backup complete."
