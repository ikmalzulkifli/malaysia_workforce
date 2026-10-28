#!/bin/bash
# Single process-supervision entrypoint. Compose owns every long-running role;
# no host systemd unit runs web/worker/scheduler/socketio.
set -euo pipefail

BENCH=/home/frappe/frappe-bench
SITE="${SITE_NAME:?SITE_NAME is required}"
ROLE="${ROLE:?ROLE is required}"

bootstrap_sites_volume() {
  # The sites directory is a named volume. Seed apps.txt and this image's built
  # assets once per image tag, and render common_site_config.json on first start.
  mkdir -p "$BENCH/sites"
  if [ ! -f "$BENCH/sites/apps.txt" ]; then
    cp /opt/seed-apps.txt "$BENCH/sites/apps.txt"
  fi
  asset_sha="$(cat /opt/assets.sha)"
  if [ ! -d "$BENCH/sites/assets" ] || [ "$(cat "$BENCH/sites/assets/.image" 2>/dev/null || true)" != "$asset_sha" ]; then
    rm -rf "$BENCH/sites/assets"
    cp -a /opt/seed-assets "$BENCH/sites/assets"
    echo "$asset_sha" > "$BENCH/sites/assets/.image"
  fi
  # Always render the managed common config: a new named volume inherits the
  # image's bench-init default, which points at localhost and has no passwords.
  envsubst '${REDIS_CACHE_PASSWORD} ${REDIS_QUEUE_PASSWORD}' \
    < /opt/common_site_config.json.template > "$BENCH/sites/common_site_config.json.tmp.$$"
  mv "$BENCH/sites/common_site_config.json.tmp.$$" "$BENCH/sites/common_site_config.json"
  chown -R frappe:frappe "$BENCH/sites"
}

prepare_site_dir() {
  # Never create the site directory here: an empty directory makes `bench new-site`
  # believe the site exists and refuse to initialise it.
  if [ ! -d "$BENCH/sites/$SITE" ]; then
    echo "Site $SITE is not initialised; run the setup service first." >&2
    exit 66
  fi
  chown -R frappe:frappe "$BENCH/sites/$SITE" 2>/dev/null || true
}

case "$ROLE" in
  setup|web|worker|scheduler|socketio)
    bootstrap_sites_volume
    ;;
esac

case "$ROLE" in
  web)
    prepare_site_dir
    cd "$BENCH/sites"
    exec gosu frappe "$BENCH/env/bin/gunicorn" \
      -b 0.0.0.0:8000 \
      -w "${GUNICORN_WORKERS:-2}" \
      --max-requests 1000 --max-requests-jitter 100 \
      -t 120 --graceful-timeout 30 \
      frappe.app:application --preload
    ;;
  worker)
    prepare_site_dir
    cd "$BENCH"
    exec gosu frappe bench worker --queue short,default,long
    ;;
  scheduler)
    prepare_site_dir
    cd "$BENCH"
    exec gosu frappe bench schedule
    ;;
  socketio)
    prepare_site_dir
    cd "$BENCH"
    exec gosu frappe bench socketio
    ;;
  setup)
    exec /opt/setup.sh
    ;;
  backup)
    exec /opt/backup.sh
    ;;
  restore)
    exec /opt/restore.sh "$@"
    ;;
  frontend)
    exec /opt/frontend/entrypoint.sh
    ;;
  *)
    echo "Unknown ROLE: $ROLE" >&2
    exit 64
    ;;
esac
