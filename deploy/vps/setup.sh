#!/bin/bash
# Idempotent one-shot setup: create the site, install pinned apps, migrate twice.
set -euo pipefail

BENCH=/home/frappe/frappe-bench
SITE="${SITE_NAME:?SITE_NAME is required}"
SITE_URL="${SITE_URL:-https://$SITE}"

mkdir -p "$BENCH/sites"
chown -R frappe:frappe "$BENCH/sites"

run() { gosu frappe "$@"; }

cd "$BENCH"
if [ ! -f "sites/$SITE/site_config.json" ]; then
  # An empty leftover directory blocks `bench new-site`; only remove empty ones.
  [ -d "sites/$SITE" ] && rmdir "sites/$SITE" 2>/dev/null || true
  run bench new-site "$SITE" \
    --db-host db --db-port 3306 \
    --db-root-username root \
    --db-root-password "$DB_ROOT_PASSWORD" \
    --admin-password "$ADMIN_PASSWORD" \
    --mariadb-user-host-login-scope='%'
fi

run bench --site "$SITE" install-app erpnext
run bench --site "$SITE" install-app hrms
run bench --site "$SITE" install-app malaysia_workforce
run bench --site "$SITE" migrate
run bench --site "$SITE" migrate
run bench --site "$SITE" set-config host_name "$SITE_URL"
run bench --site "$SITE" set-config developer_mode 0
run bench --site "$SITE" clear-cache
run bench --site "$SITE" clear-website-cache
echo "SETUP_OK $SITE"
