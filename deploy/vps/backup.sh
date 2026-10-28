#!/bin/bash
# Payroll-only logical backup: database dump + site files, checksummed.
# Never touches Nextcloud volumes or its restic repository.
set -euo pipefail

BENCH=/home/frappe/frappe-bench
SITE="${SITE_NAME:?SITE_NAME is required}"
DEST_ROOT="/backup"  # bind-mounted from ${BACKUP_DIR} on the host
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$DEST_ROOT/payroll-$STAMP"

mkdir -p "$DEST"
chmod 700 "$DEST_ROOT" "$DEST"

DB_NAME="$(python3 -c "import json,sys;print(json.load(open('$BENCH/sites/$SITE/site_config.json'))['db_name'])")"
mysqldump --host=db --user=root --password="$DB_ROOT_PASSWORD" \
  --single-transaction --quick --routines --events "$DB_NAME" > "$DEST/database.sql"
chmod 600 "$DEST/database.sql"

tar -C "$BENCH/sites/$SITE" -czf "$DEST/site-files.tgz" .
sha256sum "$DEST/database.sql" "$DEST/site-files.tgz" > "$DEST/SHA256SUMS"
echo "BACKUP_OK $DEST"
