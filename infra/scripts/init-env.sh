#!/bin/sh
# Create .env from .env.example on first run and fill empty secrets with random values.
# An existing .env is never touched.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ROOT/.env"

if [ -f "$ENV_FILE" ]; then
    exit 0
fi

umask 077
while IFS= read -r line; do
    case "$line" in
        *_PASSWORD= | JWT_SECRET= | JUDGE0_AUTHN_TOKEN= | BACKUP_PASSPHRASE=)
            if [ "$line" = "DEMO_PASSWORD=" ]; then
                echo "$line"
            else
                echo "${line}$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
            fi
            ;;
        *) echo "$line" ;;
    esac
done < "$ROOT/.env.example" > "$ENV_FILE"

echo "Created .env with generated secrets."
