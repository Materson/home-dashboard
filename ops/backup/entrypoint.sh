#!/bin/sh
# Nightly backup: mariadb-dump + /media tarball, encrypted with the passphrase
# from the environment, rotated after BACKUP_KEEP_DAYS.
#
# Runs forever inside its own container; sleeps until 03:17 every night.
set -eu

apk add --no-cache mariadb-client gnupg tar coreutils tzdata >/dev/null

: "${MARIADB_DATABASE:?}"
: "${MARIADB_USER:?}"
: "${MARIADB_PASSWORD:?}"
: "${BACKUP_PASSPHRASE:?}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

run_once() {
    stamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
    out="$BACKUP_DIR/home-$stamp.tar.gpg"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT

    echo "[backup] dumping database"
    mariadb-dump \
        --host="${DB_HOST:-db}" \
        --user="$MARIADB_USER" \
        --password="$MARIADB_PASSWORD" \
        --single-transaction --quick --routines --triggers --events \
        "$MARIADB_DATABASE" > "$tmp/db.sql"

    echo "[backup] archiving /media"
    tar -C / -cf "$tmp/media.tar" media

    echo "[backup] encrypting → $out"
    tar -C "$tmp" -cf - db.sql media.tar \
      | gpg --batch --yes --symmetric --cipher-algo AES256 \
            --passphrase "$BACKUP_PASSPHRASE" -o "$out"

    echo "[backup] rotating older than $KEEP_DAYS day(s)"
    find "$BACKUP_DIR" -type f -name 'home-*.tar.gpg' -mtime "+$KEEP_DAYS" -delete

    rm -rf "$tmp"
    trap - EXIT
}

# If the container was told to run once (for ad-hoc), honor it.
if [ "${RUN_ONCE:-0}" = "1" ]; then
    run_once
    exit 0
fi

while true; do
    now="$(date +%s)"
    # next 03:17 local time
    next="$(date -d 'today 03:17' +%s 2>/dev/null || date +%s)"
    if [ "$next" -le "$now" ]; then
        next="$(date -d 'tomorrow 03:17' +%s)"
    fi
    sleep_for=$(( next - now ))
    echo "[backup] sleeping ${sleep_for}s until $(date -d "@$next")"
    sleep "$sleep_for"
    run_once || echo "[backup] run failed — will try again tomorrow"
done
