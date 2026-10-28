# Malaysia Workforce — private VPS pilot (Ocean6 Nextcloud host)

Status: **deployment files only.** No host change, DNS record, firewall rule,
resize or live payroll is authorised by this document.

## What this stack is

A separate Compose project, `ocean6-payroll`, running the pinned stack
(Frappe 16.31.0, ERPNext 16.31.1, HRMS 16.16.0, MariaDB 11.4.13, Python 3.14)
plus this app. It shares no database, Redis, credentials or volumes with
Nextcloud. Its only contact with the Nextcloud stack is a single Caddy site
block that proxies `payroll.theocean6.com` to this project's frontend.

## Isolation

| Resource | Value |
|---|---|
| Compose project | `ocean6-payroll` |
| Network (internal) | `payroll_internal`, 172.30.61.0/24, no published ports |
| Ingress network | external `ocean6-nextcloud_default` (frontend only) |
| Database | `payroll_db` volume, MariaDB 11.4.13, no host port |
| Cache Redis | `redis-cache`, LRU, no persistence, internal only |
| Queue Redis | `redis-queue`, `noeviction`, AOF everysec, `payroll_redis_queue` volume |
| Site data | `payroll_site` volume at `sites/<SITE_NAME>` (site_config, private/public files) |
| Configuration | `sites/common_site_config.json` inside the `payroll_sites` volume, rendered from env on first start |
| Secrets | `${RUNTIME_DIR}/payroll.env` (0600 root, never committed) |
| Backups | `${BACKUP_DIR}/payroll-<UTC stamp>/` (root 0700) |

Process supervision: **Compose only** for web, worker, scheduler and Socket.IO.
No systemd unit supervises those processes, so there is one owner and no
duplicate workers or schedulers. A systemd timer may only trigger the one-shot
backup service (`docker compose run --rm backup`); it does not supervise an app
process.

## Prerequisites (each needs explicit approval where marked)

1. **[approval] Capacity gate.** Run the read-only preflight from an authorised
   operator session and record: `MemAvailable`, swap, `df -h`, `docker stats`,
   listening ports, Compose state, Nextcloud backup timer/journal. The pilot
   proceeds on the 4 GB instance only if `MemAvailable` ≥ 1,500 MB at steady
   state and disk free ≥ 15 GB. Otherwise the pilot does **not** proceed; a
   resize or separate instance is a separate decision, not part of this plan.
2. **[approval] Access IPs.** From the operator machine run
   `curl -s https://ifconfig.me` and confirm the current public IP. Do not reuse
   `14.192.215.38` on assumption. The Caddy snippet's `__PILOT_ALLOW_CIDR__`
   must be replaced with the verified value(s).
3. **[approval] DNS.** `payroll.theocean6.com` has no record today. An A record
   to `54.169.121.28` is required before Caddy can obtain a certificate.
4. **[approval] Snapshot.** Confirm a recent Lightsail auto-snapshot; take a
   manual snapshot before the ingress change if policy requires it.
5. PDF renderer: the image ships `wkhtmltopdf`; the app selects it when present.
6. Build the image for the VPS architecture and push or load it:
   `docker build --platform linux/amd64 -f deploy/vps/Dockerfile -t ocean6-payroll:pilot-<commit> .`
   Tag the image with the commit SHA being deployed, and set `APP_IMAGE_TAG`
   to the same value in `payroll.env`.
   The Lightsail instance is x86_64; a workstation build is usually arm64.
   Build with `--platform linux/amd64` (or on an amd64 builder) and verify the
   image runs before loading it on the host.

## Deploy (exact commands, run on the host from the payroll runtime directory)

```bash
# 0. Files (root-owned; payroll-owned paths only)
install -d -m 0700 /opt/ocean6-payroll/runtime /var/lib/ocean6-payroll-backup
# copy compose.yaml, common_site_config.json.template, Caddyfile.payroll,
# entrypoint/setup/backup/restore scripts here (or run from a checkout).

# 1. Secrets
cd /opt/ocean6-payroll/runtime
cp payroll.env.example payroll.env && chmod 0600 payroll.env
# edit payroll.env: SITE_NAME, SITE_URL, RUNTIME_DIR, BACKUP_DIR, APP_IMAGE_TAG,
# and generate DB_ROOT_PASSWORD, DB_PASSWORD, REDIS_CACHE_PASSWORD,
# REDIS_QUEUE_PASSWORD, ADMIN_PASSWORD (openssl rand -base64 32 is fine).
# The setup role renders sites/common_site_config.json inside the payroll_sites
# volume and percent-encodes the Redis credentials, so any password is valid.
# Setup is the single writer of shared assets and config; app roles only verify.

# 2. Infrastructure services first
docker compose --env-file payroll.env -f compose.yaml up -d db redis-cache redis-queue

# 3. Create the site and install pinned apps (idempotent)
docker compose --env-file payroll.env -f compose.yaml run --rm setup

# 4. Application services
docker compose --env-file payroll.env -f compose.yaml up -d web worker scheduler socketio frontend

# 5. Ingress (one appended block; back up first)
NC=/opt/ocean6-nextcloud/runtime
cp "$NC/Caddyfile" "$NC/Caddyfile.bak-$(date -u +%Y%m%dT%H%M%SZ)"
# replace __PILOT_ALLOW_CIDR__ with the verified IP, then append Caddyfile.payroll
NC=/opt/ocean6-nextcloud/runtime
docker compose -p ocean6-nextcloud --env-file "$NC/runtime.env" -f "$NC/compose.yaml" \
  exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## Native amd64 build (VPS architecture)

The Lightsail instance is `linux/amd64`; a workstation Docker build is usually
arm64. Do not use QEMU emulation (`uv`/CPython builds fail). Use a native amd64
host, in this order of preference:

1. **Operator amd64 machine** (existing hardware):
   `docker build --platform linux/amd64 -f deploy/vps/Dockerfile -t ocean6-payroll:pilot-<commit> .`
2. **Existing GitHub Actions amd64 runner** (ubuntu-latest is native amd64):
   requires pushing the commit and approving a workflow run; upload the image as
   a workflow artifact with `docker save`, not to a registry. The manual
   `.github/workflows/amd64-release.yml` job builds the image, then runs, on that
   native amd64 artifact: image smoke, site setup/startup, the payroll scenario,
   HTTPS login with `Secure`/`HttpOnly` cookie and session identity, authenticated
   payslip PDF, private-file denial for guest and unrelated employee, queue
   recovery across a `redis-queue` restart, user-scoped only realtime delivery
   (after restarting `socketio`), and the scratch-restore guards (67/68/69/OK).
   It uploads `digest.txt`, the `docker save` archive and `scenario.json`.
3. **The Lightsail host itself** (x86_64): only after capacity readings and
   explicit approval, because the build is CPU/disk heavy and shares the host
   with Nextcloud. Do not build there while Nextcloud is in use.

Record the artifact:

```bash
docker image inspect ocean6-payroll:pilot-<commit>   --format 'id={{.Id}} arch={{.Os}}/{{.Architecture}} created={{.Created}}'
docker save ocean6-payroll:pilot-<commit> | gzip > payroll-<commit>-amd64.tar.gz
sha256sum payroll-<commit>-amd64.tar.gz
```

Load on the host with `gunzip -c … | docker load`, confirm
`docker image inspect --format '{{.Os}}/{{.Architecture}}'` is `linux/amd64`,
then set `APP_IMAGE_TAG=pilot-<commit>` in `payroll.env`.

## Realtime after a Redis restart

The realtime server's Redis subscriber does not always recover when
`redis-queue`/`redis-cache` restarts; user-scoped events stop arriving until the
`socketio` service is restarted. Restart `socketio` after any Redis restart and
re-run the user-scoped event check.

## Asset fetching for PDFs

wkhtmltopdf renders print HTML and fetches `/assets/...` from the site URL. The
compose file maps `${SITE_NAME}` to the host gateway (`extra_hosts`), so the
request reaches the host's Caddy even when public DNS or NAT hairpin is
unavailable. The site hostname must have a certificate valid for that name.

## Local validation findings (baked into these files)

- MariaDB healthcheck must be `healthcheck.sh --connect`; `--innodb` is rejected by mariadb:11.4.
- `bench new-site` needs explicit `--db-host db --db-port 3306`; the common config alone was not honoured in this bench version.
- A new named volume inherits the image's `sites/` (bench-init default), so `common_site_config.json` must be rendered on every start and the asset seed must be refreshed by a content hash, not only an image tag.
- `bench build` cannot run in the runtime image (no yarn). Assets are built in the builder; never rebuild them on the host.
- A stale Redis `assets_json` entry can survive a volume re-seed; setup clears the cache, and a restart of `web` after an asset change is required.
- Gunicorn is started directly (not via Frappe's development `serve()` ProxyFix), so it only honours `X-Forwarded-Proto` from `TRUSTED_PROXY_IP`. The frontend has a fixed internal address (`FRONTEND_INTERNAL_IP`); keep both values equal and never use `*`.

## Acceptance (fictional data only)

```bash
SITE=payroll.theocean6.com
H="Host: $SITE"
# web
curl -fsS -H "$H" https://$SITE/api/method/ping
# assets (pick a real bundle from sites/assets/assets.json)
curl -fsS -H "$H" -o /dev/null -w '%{http_code}\n' https://$SITE/assets/frappe/js/frappe-web.bundle.js
# socket.io handshake
curl -fsS -H "$H" "https://$SITE/socket.io/?EIO=4&transport=polling" | head -c 80
# private file requires a session; unauthenticated must be 403/redirect
curl -s -o /dev/null -w '%{http_code}\n' -H "$H" https://$SITE/private/files/does-not-exist
# workers and scheduler
docker compose --env-file payroll.env -f compose.yaml logs --tail=50 worker scheduler
docker compose --env-file payroll.env -f compose.yaml exec web bench --site $SITE doctor
# payroll scenarios (fictional data)
docker compose --env-file payroll.env -f compose.yaml exec web \
  bench --site $SITE execute malaysia_workforce.live_tests.scenarios.run_payroll_fixes
# PDF
docker compose --env-file payroll.env -f compose.yaml exec web \
  bench --site $SITE execute frappe.utils.pdf.get_pdf --kwargs '{"html":"<p>pilot</p>"}' >/tmp/p.pdf
head -c 4 /tmp/p.pdf   # %PDF
# Nextcloud unaffected
curl -fsS https://drive.theocean6.com/status.php
```

Queue persistence check (no eviction, survives restart):

```bash
docker compose --env-file payroll.env -f compose.yaml stop worker
docker compose --env-file payroll.env -f compose.yaml exec web bench --site $SITE \
  execute frappe.enqueue --kwargs '{"method":"frappe.db.set_value","queue":"default","doctype":"Company","name":"Pilot Test Sdn Bhd","fieldname":"company_description","value":"queue-survived"}'
docker compose --env-file payroll.env -f compose.yaml restart redis-queue
docker compose --env-file payroll.env -f compose.yaml start worker
# then confirm company_description is queue-survived
```

Backup and restore (scratch restore, never over the live DB):

```bash
docker compose --env-file payroll.env -f compose.yaml run --rm backup
# restore is scratch-only: choose a NEW payroll_restore_* database name
docker compose --env-file payroll.env -f compose.yaml run --rm \
  -e RESTORE_TARGET_DB=payroll_restore_1 restore /backup/payroll-<stamp>
```

## Rollback (non-destructive)

```bash
# 1. Ingress: restore the Caddyfile backup and reload
cp /opt/ocean6-nextcloud/runtime/Caddyfile.bak-<stamp> /opt/ocean6-nextcloud/runtime/Caddyfile
NC=/opt/ocean6-nextcloud/runtime
docker compose -p ocean6-nextcloud --env-file "$NC/runtime.env" -f "$NC/compose.yaml" \
  exec caddy caddy reload --config /etc/caddy/Caddyfile

# 2. Payroll containers and network only; volumes and config are preserved
cd /opt/ocean6-payroll/runtime
docker compose --env-file payroll.env -f compose.yaml down

# 3. Verify Nextcloud
curl -fsS https://drive.theocean6.com/status.php
```

`down` (without `-v`) keeps `payroll_db`, `payroll_redis_queue`, `payroll_sites`,
`common_site_config.json` (inside the volume), `payroll.env` and every backup. **Deleting any of
those is a data-destruction step requiring separate written approval.** Do not
run `down -v`, `docker volume rm`, or remove `/var/lib/ocean6-payroll-backup`
as part of a rollback.

## Not included / not authorised

Resize, replacement instance, DNS record, firewall changes, live payroll,
payslip sending, statutory submission, historical employee data, employer
journal treatment, authority-file acceptance, zero/zero CP39 handling and
HASiL verification.
