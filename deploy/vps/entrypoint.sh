#!/bin/bash
# Single process-supervision entrypoint. Compose owns every long-running role;
# no host systemd unit runs web/worker/scheduler/socketio.
set -euo pipefail

BENCH=/home/frappe/frappe-bench
SITE="${SITE_NAME:?SITE_NAME is required}"
ROLE="${ROLE:?ROLE is required}"

bootstrap_sites_volume() {
  # Single writer: only the setup role seeds shared assets, apps.txt and the
  # common config. Application roles verify and never write shared state.
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
  python3 - "$BENCH/sites/common_site_config.json" <<'PYCFG'
import json, os, sys
from urllib.parse import quote

def redis_url(host, db, variable):
    value = os.environ.get(variable, "")
    if not value:
        raise SystemExit(f"{variable} must be set")
    return f"redis://:{quote(value, safe='')}@{host}:6379/{db}"

config = {
    "db_host": "db",
    "redis_cache": redis_url("redis-cache", 0, "REDIS_CACHE_PASSWORD"),
    "redis_queue": redis_url("redis-queue", 1, "REDIS_QUEUE_PASSWORD"),
    "redis_socketio": redis_url("redis-cache", 2, "REDIS_CACHE_PASSWORD"),
    "serve_default_site": True,
    "gunicorn_workers": int(os.environ.get("GUNICORN_WORKERS", "2")),
    "webserver_port": 8000,
    "socketio_port": 9000,
}
target = sys.argv[1]
tmp = target + ".tmp"
with open(tmp, "w", encoding="utf-8") as handle:
    json.dump(config, handle, indent=2)
os.replace(tmp, target)
PYCFG
  chown -R frappe:frappe "$BENCH/sites"
}

require_initialised() {
  # Application roles are readers. A missing seed means setup has not run.
  [ -f "$BENCH/sites/common_site_config.json" ] || {
    echo "Payroll stack not initialised: run the setup service first." >&2; exit 66; }
  [ -d "$BENCH/sites/$SITE" ] || {
    echo "Site $SITE missing: run the setup service first." >&2; exit 66; }
  [ -d "$BENCH/sites/assets" ] || {
    echo "Assets missing: run the setup service first." >&2; exit 66; }
}

case "$ROLE" in
  setup)
    bootstrap_sites_volume
    ;;
  web|worker|scheduler|socketio)
    require_initialised
    ;;
esac

case "$ROLE" in
  web)
    cd "$BENCH/sites"
    exec gosu frappe "$BENCH/env/bin/gunicorn" \
      -b 0.0.0.0:8000 \
      -w "${GUNICORN_WORKERS:-2}" \
      --max-requests 1000 --max-requests-jitter 100 \
      -t 120 --graceful-timeout 30 \
      --forwarded-allow-ips="${TRUSTED_PROXY_IP:?TRUSTED_PROXY_IP is required}" \
      frappe.app:application --preload
    ;;
  worker)
    cd "$BENCH"
    exec gosu frappe bench worker --queue short,default,long
    ;;
  scheduler)
    cd "$BENCH"
    exec gosu frappe bench schedule
    ;;
  socketio)
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
