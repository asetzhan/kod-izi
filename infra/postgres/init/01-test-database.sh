#!/bin/sh
# Runs once, when the database volume is created: a separate database for `make test`.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "CREATE DATABASE \"${POSTGRES_DB}_test\""
