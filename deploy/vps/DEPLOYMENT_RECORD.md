# Deployment record — Ocean6 payroll pilot (fictional data)

Recorded from the actual deployment, not from a plan. All dates UTC unless
noted. No secrets are recorded here; the runtime env file holds them.

## Identity

| Field | Value |
|---|---|
| Public URL | `https://hr.theocean6.com` |
| DNS | `hr.theocean6.com` A → `54.169.121.28` (zone `theocean6.com` is hosted at the registrar, `ns137/ns138.mschosting.cloud`; **not** Route 53) |
| Certificate | Let's Encrypt, `CN=hr.theocean6.com`, valid 2026-10-28 → 2027-01-26 |
| Host | `ocean6-nextcloud-sg`, `ap-southeast-1a`, Ubuntu 24.04.4 LTS, `7.0.0-1012-aws`, x86_64 |
| Host sizing | 2 vCPU, 3,832 MB RAM, 77 GB root volume, dual-stack (static IPv4 `54.169.121.28`) |
| Source commit | `e80c07a` (checked out at `/opt/ocean6-payroll/src`) |
| Image | `ocean6-payroll:pilot-e80c07a`, `linux/amd64`, 3,052,881,199 bytes |
| Archive | `payroll-amd64-e80c07a.tar.gz`, 1,028,640,216 bytes |
| Archive SHA-256 | `57450611769827c3a54fc4e5ab3e1aa5ed24e4349ad0f250db3114c4558bb58b` |
| Image config digest | `ebc72cbbceb5bb1e23242719ec23f0e556ffd32bd78153a4459e6a83196809e1` |
| OCI manifest digest (`.Id` on a containerd store) | `725934c0cdba2d1e27a72b4eacedcda405ae3d4786fa936c906e66c0c305470e` |

The archive digest and the image config digest were re-verified **on the host**
after transfer. The `.Id` reported by `docker image inspect` on this host is the
OCI manifest digest, not the config digest; both describe the same image.

## Layout on the host

| Path | Purpose |
|---|---|
| `/opt/ocean6-payroll/src` | checkout of `e80c07a` (compose + deploy scripts) |
| `/opt/ocean6-payroll/runtime/payroll.env` | runtime configuration and generated secrets, `0600 root` |
| `/var/lib/ocean6-payroll-backup/payroll-<UTC stamp>/` | backup snapshots, `root 0700` |
| Compose project | `ocean6-payroll` (db, redis-cache, redis-queue, web, worker, scheduler, socketio, frontend) |
| Networks | `payroll_internal` 172.30.61.0/24 (all services), external `ocean6-nextcloud_default` (frontend only, fixed IP 172.30.61.10 on the internal leg) |

No payroll container publishes a host port. The only external surface is the
Caddy site block on the Nextcloud Caddy (`80`/`443`).

## Ingress

```
hr.theocean6.com {
    header Strict-Transport-Security "max-age=15552000"
    @pilot remote_ip 14.192.214.111/32 172.30.60.0/24 172.30.61.0/24
    handle @pilot { reverse_proxy ocean6-payroll-frontend:8080 }
    handle { respond "Not available" 403 }
}
```

- `14.192.214.111/32` — the verified operator address at deployment time. Add or
  replace per pilot tester; never widen to `0.0.0.0/0`.
- `172.30.60.0/24` and `172.30.61.0/24` — internal only, required because
  `web`/`worker` render payslip PDFs and fetch `/assets` from the site URL
  through this block. They admit internal container traffic; they do **not**
  bypass Frappe authentication (sessions, roles, permissions and private-file
  checks all still apply). Without them, PDF download fails with HTTP 417 and
  `wkhtmltopdf … ContentAccessDenied`.

## Gate readings before deployment (pre-stack)

| Reading | Value | Gate |
|---|---|---|
| `MemAvailable` | 2,849 MB | ≥ 1,500 MB — pass |
| Swap | 0 MB (no swap) | informational |
| Disk free on `/` | 70 GB of 77 GB (10 % used) | ≥ 15 GB — pass |
| Nextcloud containers | 5/5 up, ~326 MB RSS combined | healthy |
| Nextcloud backup timer | last run 22 h prior, next scheduled | healthy |
| Lightsail snapshots | daily auto-snapshot `Success`, newest ~19 h old | recovery confirmed |

## Acceptance after deployment (fictional data)

| Check | Result |
|---|---|
| HTTPS/TLS | `GET /` 200; `api/method/ping` → `pong`; LE certificate for the host |
| Login | 200; `sid … Secure; HttpOnly; Path=/; SameSite=Lax`; identity returned |
| Payroll scenario | 78 checks, 0 failed |
| Payslip PDF | 200, 27,990 bytes, `%PDF-` … `%%EOF` |
| Private file | guest 403, unrelated employee 403, owner 200 |
| Queue recovery | worker stopped → job queued → `redis-queue` restarted → worker started → job applied |
| Realtime | site-wide event received by both signed-in users; user-scoped event received only by the target user; guest rejected at namespace auth; user-scoped delivery resumed after the documented `socketio` restart |
| Scratch restore | tampered 67, existing DB 68 (marker intact), existing extraction dir 69 (marker intact), fresh restore OK |
| Nextcloud | `status.php` healthy before, during and after the changes |

Test fixtures created for acceptance (two QA users) were deleted, scratch restore
databases were dropped, the tampered backup copy was removed, and the deployment
left one backup snapshot in place.

## Post-deployment resource baseline — PENDING (host access unavailable)

Status at `2026-10-29T00:12:32Z`: **not measured.** The steady-state reading after
the stack started has not been taken, because no authorised host path exists from
the deployment workstation:

- Lightsail port state: `22 → 14.192.215.38/32` only (no IPv6 rule). The
  workstation egress is `14.192.214.111`, so SSH is refused at the firewall.
- Lightsail browser SSH requires an inbound SSH rule allowing any address; it is
  deliberately closed again after deployment, and re-opening it is a firewall
  change that this closeout does not authorise.
- There is no SSM agent or CloudShell route into a Lightsail guest, and the
  Lightsail API exposes CPU/network metrics only — not memory, swap or disk.

Consequently the pre-deployment `MemAvailable` of 2,849 MB remains the last valid
reading, and it **excludes** the eight `ocean6-payroll` containers. Post-stack
headroom is unknown; do not treat 2,849 MB as current.

### What is measured vs. what would be inferred

| Reading | What it actually tells you |
|---|---|
| `MemAvailable` (instant) | Current headroom only; not a peak or a trend |
| `docker stats --no-stream` | One instantaneous sample per container; RSS includes page cache the kernel can reclaim |
| `docker inspect … State.OOMKilled` | Whether **this** container instance was OOM-killed; `false` does **not** prove no OOM ever occurred, since a restart replaces the state object |
| `docker inspect … RestartCount` | Restarts since this container was created, not since boot; a recreated container resets it |
| `journalctl -k \| grep -i oom` | Kernel OOM-killer events (bounded `--since`), the only direct historical evidence |
| `docker events --since …` | Historical restart/die/kill events, if the daemon still has them buffered |

Acceptable evidence of "no OOM" is: no kernel OOM lines in a bounded window, no
`die`/`restart` events, `RestartCount=0`, and `MemAvailable` comfortably above
the threshold — not `OOMKilled=false` on its own.

### To be collected from an authorised session (read-only, no load)

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
grep -E 'MemTotal|MemAvailable|SwapTotal|SwapFree' /proc/meminfo
df -h / /var/lib/docker
sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | sort
sudo docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
sudo docker inspect $(sudo docker ps -aq) \
  --format '{{.Name}} restarts={{.RestartCount}} oom={{.State.OOMKilled}} exit={{.State.ExitCode}}'
journalctl -k --since "-7 days" | grep -iE "out of memory|oom-kill" || echo "no kernel OOM lines"
sudo docker events --since 168h --until 0s --filter event=die --filter event=restart --format '{{.Time}} {{.Actor.Attributes.name}} {{.Status}}' | tail -20
```

Record the timestamp with the numbers: two samples an hour apart are more useful
than one, and both are needed before any claim about steady state.

### Risk to watch once measured

The host has **no swap** and ~3.8 GB RAM total, and now runs both stacks. A
sustained `MemAvailable` below ~800 MB, any `OOMKilled=true`, new kernel OOM
lines, or a rising `RestartCount` are the signals to act on. The mitigation is a
resize or a second instance — not squeezing this one, and not disabling Nextcloud
features to make room.

### Read-only health confirmed externally (no host access used)

At `2026-10-29T00:12:32Z`: `https://hr.theocean6.com/api/method/ping` → `pong`;
`GET https://hr.theocean6.com/` → `200`; `https://drive.theocean6.com/status.php`
→ `installed true`, `maintenance false`, `v35.0.2`. This proves both reverse-proxy
paths serve traffic; it says nothing about memory.

## Known advisories on the host (not caused by this deployment)

- Lightsail advisory: **PHP CVE-2026-109618 / CVE-2026-109619** affects the
  Nextcloud PHP image; update out of band.
- `*** System restart required ***` with 39 pending package updates.
- No swap configured.

## Transfer and handling notes

- The verified archive was uploaded to the existing private bucket
  `ocean6-nextcloud-backups-072718159723-sg` under a `tmp-transfer/` key with
  SSE-S3; the bucket keeps public access fully blocked.
- It was fetched on the host with a 30-minute presigned GET URL supplied through
  a silent (`read -rs`) prompt, and the SHA-256 was verified on the host.
- The temporary object version was deleted; `list-object-versions` and
  `list-multipart-uploads` for `tmp-transfer/` both return 0.
- Handling incident: during the transfer, a presigned URL was displayed once in
  the console terminal because of a clipboard sequencing error. The object was
  deleted immediately, which made the URL useless; the embedded temporary
  session token remains valid until it expires. Rotate the workstation
  credentials if that matters for the engagement.
- Temporary SSH access used for deployment (world-open IPv4/IPv6) was removed
  afterwards and the original rule (`22` from `14.192.215.38/32`) restored;
  verified from outside that port 22 is closed again.

## Rollback

See `README.md` → Rollback. Summary: restore the Caddyfile backup **in place**
and `restart` Caddy (a `reload` cannot re-bind a replaced inode), then
`docker compose … down` for project `ocean6-payroll`. Volumes, backups and
`payroll.env` are preserved; `down -v` and `docker volume rm` are
data-destruction steps requiring separate written approval. Verify Nextcloud
afterwards.
