#!/bin/sh
# Daily encrypted backup (spec 13, 14.1): database dump and teaching material files.
#
# Environment: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE (standard libpq variables),
# BACKUP_PASSPHRASE (required), BACKUP_DIR (default /backups),
# MATERIAL_DIR (optional, default /data/materials), BACKUP_KEEP_DAYS (default 30).
set -eu

: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$BACKUP_DIR"

encrypt() {
    openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$1"
}

DB_FILE="$BACKUP_DIR/kodizi-db-$STAMP.dump.enc"
pg_dump --format=custom --no-owner | encrypt "$DB_FILE"

MATERIAL_DIR="${MATERIAL_DIR:-/data/materials}"
if [ -d "$MATERIAL_DIR" ]; then
    tar -C "$MATERIAL_DIR" -cf - . | encrypt "$BACKUP_DIR/kodizi-files-$STAMP.tar.enc"
fi

(cd "$BACKUP_DIR" && sha256sum kodizi-*-"$STAMP".* > "kodizi-$STAMP.sha256")
find "$BACKUP_DIR" -name 'kodizi-*' -type f -mtime +"${BACKUP_KEEP_DAYS:-30}" -delete
echo "backup written: $DB_FILE"
