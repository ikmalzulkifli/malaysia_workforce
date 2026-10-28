#!/bin/bash
# Restore a payroll backup. Default target is a SCRATCH database; restoring over
# the live site requires an explicit RESTORE_TARGET_DB plus separate approval.
set -euo pipefail

SRC="${1:?usage: restore.sh <backup-dir>}"
TARGET_DB="${RESTORE_TARGET_DB:-payroll_restore_$(date -u +%s)}"
BENCH=/home/frappe/frappe-bench

[ -f "$SRC/database.sql" ] || { echo "missing $SRC/database.sql" >&2; exit 66; }
[ -f "$SRC/site-files.tgz" ] || { echo "missing $SRC/site-files.tgz" >&2; exit 66; }
( cd "$SRC" && sha256sum -c SHA256SUMS )

mysql --host=db --user=root --password="$DB_ROOT_PASSWORD" \
  -e "DROP DATABASE IF EXISTS \`$TARGET_DB\`; CREATE DATABASE \`$TARGET_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql --host=db --user=root --password="$DB_ROOT_PASSWORD" "$TARGET_DB" < "$SRC/database.sql"

EXTRACT="${RESTORE_FILES_DIR:-/tmp/payroll-restore-$TARGET_DB}"
mkdir -p "$EXTRACT"
tar -C "$EXTRACT" -xzf "$SRC/site-files.tgz"
echo "RESTORE_OK db=$TARGET_DB files=$EXTRACT"
