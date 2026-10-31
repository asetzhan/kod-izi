#!/bin/sh
# Restore a backup made by backup.sh into the database named by the libpq variables.
#
#   restore.sh /backups/kodizi-db-20261101T020000Z.dump.enc [/backups/kodizi-files-...tar.enc]
#
# BACKUP_PASSPHRASE is required. The target database must exist; existing objects are
# replaced. MATERIAL_DIR receives the files when a file archive is given.
set -eu

: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required}"
DB_FILE="${1:?usage: restore.sh DB_BACKUP [FILES_BACKUP]}"

decrypt() {
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$1"
}

SUMS="$(dirname "$DB_FILE")/kodizi-$(basename "$DB_FILE" | sed 's/^kodizi-db-//; s/\.dump\.enc$//').sha256"
if [ -f "$SUMS" ]; then
    (cd "$(dirname "$DB_FILE")" && sha256sum --check --ignore-missing "$(basename "$SUMS")")
fi

# Grants in the dump refer to the application role (row-level security, migration 0006).
psql --quiet --dbname "${PGDATABASE:?PGDATABASE is required}" -c \
    "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kodizi_app')
     THEN CREATE ROLE kodizi_app NOLOGIN; END IF; END \$\$"

decrypt "$DB_FILE" | pg_restore --clean --if-exists --no-owner --exit-on-error \
    --dbname "$PGDATABASE"

if [ "${2:-}" != "" ]; then
    MATERIAL_DIR="${MATERIAL_DIR:-/data/materials}"
    mkdir -p "$MATERIAL_DIR"
    decrypt "$2" | tar -C "$MATERIAL_DIR" -xf -
fi
echo "restored into $PGDATABASE"
