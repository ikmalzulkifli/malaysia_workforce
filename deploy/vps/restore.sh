#!/bin/bash
# Scratch-only restore. Never drops or overwrites an existing database.
# The target must be a new database named payroll_restore_*.
set -euo pipefail

SRC="${1:?usage: restore.sh <backup-dir>  (container path, usually /backup/payroll-<stamp>)}"
TARGET_DB="${RESTORE_TARGET_DB:-}"
BENCH=/home/frappe/frappe-bench

[ -n "$TARGET_DB" ] || { echo "RESTORE_TARGET_DB is required (new scratch database name)" >&2; exit 64; }
case "$TARGET_DB" in
  payroll_restore_*) ;;
  *) echo "refusing: target database must start with payroll_restore_" >&2; exit 64 ;;
esac
if ! [[ "$TARGET_DB" =~ ^[A-Za-z0-9_]{1,48}$ ]]; then
  echo "refusing: target database name contains unsupported characters" >&2
  exit 64
fi

[ -f "$SRC/database.sql" ] || { echo "missing $SRC/database.sql" >&2; exit 66; }
[ -f "$SRC/site-files.tgz" ] || { echo "missing $SRC/site-files.tgz" >&2; exit 66; }
[ -f "$SRC/SHA256SUMS" ] || { echo "missing $SRC/SHA256SUMS" >&2; exit 66; }

# Checksums are relative to the selected backup directory, so a copied or
# modified backup is verified against its own files, not the originals.
( cd "$SRC" && sha256sum -c SHA256SUMS ) || { echo "checksum verification failed for $SRC" >&2; exit 67; }

EXISTS="$(MYSQL_PWD="$DB_ROOT_PASSWORD" mysql --host=db --user=root --batch --skip-column-names \
  -e "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='$TARGET_DB'")"
if [ -n "$EXISTS" ]; then
  echo "refusing: database $TARGET_DB already exists; choose a new payroll_restore_* name" >&2
  exit 68
fi

MYSQL_PWD="$DB_ROOT_PASSWORD" mysql --host=db --user=root \
  -e "CREATE DATABASE \`$TARGET_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
MYSQL_PWD="$DB_ROOT_PASSWORD" mysql --host=db --user=root "$TARGET_DB" < "$SRC/database.sql"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EXTRACT="${RESTORE_FILES_DIR:-/tmp/payroll-restore-$TARGET_DB-$STAMP}"
case "$EXTRACT" in
  /tmp/payroll-restore-*) ;;
  *) echo "refusing: extraction path must start with /tmp/payroll-restore-" >&2; exit 64 ;;
esac
case "$EXTRACT" in
  *..*) echo "refusing: extraction path may not contain .." >&2; exit 64 ;;
esac
PARENT="$(dirname "$EXTRACT")"
[ -d "$PARENT" ] && [ ! -L "$PARENT" ] || {
  echo "refusing: extraction parent $PARENT is missing or a symlink" >&2; exit 64; }
if [ -e "$EXTRACT" ] || [ -L "$EXTRACT" ]; then
  echo "refusing: extraction path $EXTRACT already exists" >&2
  exit 69
fi
# Create a fresh private directory; mkdir fails if another process wins the race.
mkdir -m 0700 "$EXTRACT" || { echo "refusing: could not create $EXTRACT" >&2; exit 69; }
[ ! -L "$EXTRACT" ] || { echo "refusing: extraction path became a symlink" >&2; exit 64; }
tar -C "$EXTRACT" -xzf "$SRC/site-files.tgz"
echo "RESTORE_OK db=$TARGET_DB files=$EXTRACT"
