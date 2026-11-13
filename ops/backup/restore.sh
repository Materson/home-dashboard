#!/bin/sh
# restore <backup file> — put a backup back: the database and the uploaded
# files are REPLACED with the backup's (docs/deploy-nas.md → Restore).
#
# First stop backend, worker, beat and web (Portainer → Containers → Stop),
# then in this container's Console:  restore /backups/home-<date>.tar.gpg
# Afterwards start the backend (it migrates if the backup is older), then
# the rest.
set -eu

file="${1:-}"
if [ -z "$file" ] || [ ! -f "$file" ]; then
    echo "usage: restore /backups/home-<date>.tar.gpg" >&2
    echo "backups here:" >&2
    ls -1t /backups/home-*.tar.gpg 2>/dev/null | head -10 >&2 || true
    exit 2
fi
: "${MARIADB_DATABASE:?}" "${MARIADB_USER:?}" "${MARIADB_PASSWORD:?}" "${BACKUP_PASSPHRASE:?}"
DB_HOST="${DB_HOST:-db}"

echo "This REPLACES the database '$MARIADB_DATABASE' and all uploaded files"
echo "with the backup $file."
printf "Type YES to go on: "
read -r answer
[ "$answer" = "YES" ] || { echo "Nothing changed."; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "[restore] decrypting"
gpg --batch --yes --passphrase "$BACKUP_PASSPHRASE" -d "$file" | tar -x -C "$tmp"

echo "[restore] database: emptying, then importing"
# A fresh database, so tables from a newer version don't stay behind.
mariadb --host="$DB_HOST" --user="$MARIADB_USER" --password="$MARIADB_PASSWORD" -e \
    "DROP DATABASE IF EXISTS \`$MARIADB_DATABASE\`;
     CREATE DATABASE \`$MARIADB_DATABASE\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mariadb --host="$DB_HOST" --user="$MARIADB_USER" --password="$MARIADB_PASSWORD" \
    "$MARIADB_DATABASE" < "$tmp/db.sql"

echo "[restore] uploaded files"
find /media -mindepth 1 -delete
tar -x -C / -f "$tmp/media.tar"

echo "[restore] done — start the backend now (it migrates if needed), then worker, beat and web."
