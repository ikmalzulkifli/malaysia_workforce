# syntax=docker/dockerfile:1.7
# Malaysia Workforce production image: pinned Frappe/ERPNext/HRMS + the app.
# Build context: repository root. Build: docker build -f deploy/vps/Dockerfile -t ocean6-payroll:<tag> .

FROM node:24-bookworm AS node

FROM python:3.14-slim-bookworm AS builder
ENV DEBIAN_FRONTEND=noninteractive \
    BENCH_DISABLE_UV=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates pkg-config build-essential libmariadb-dev \
      libffi-dev libssl-dev libjpeg62-turbo-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && npm install -g yarn@1.22.22
RUN pip install --no-cache-dir frappe-bench==5.31.1
RUN useradd -m -u 1000 frappe
USER frappe
ENV HOME=/home/frappe
WORKDIR /home/frappe
RUN bench init --frappe-branch v16.31.0 --skip-redis-config-generation --skip-assets --no-backups frappe-bench
WORKDIR /home/frappe/frappe-bench
RUN bench get-app --branch v16.31.1 https://github.com/frappe/erpnext \
 && bench get-app --branch v16.16.0 https://github.com/frappe/hrms
# Copy only what the app needs; the build context is restricted by .dockerignore.
COPY --chown=frappe:frappe pyproject.toml package.json README.md license.txt /home/frappe/frappe-bench/apps/malaysia_workforce/
COPY --chown=frappe:frappe malaysia_workforce /home/frappe/frappe-bench/apps/malaysia_workforce/malaysia_workforce
RUN printf "frappe\nerpnext\nhrms\nmalaysia_workforce\n" > sites/apps.txt \
 && mkdir -p apps/malaysia_workforce/node_modules \
 && env/bin/pip install -e apps/malaysia_workforce
RUN bench build --production

FROM python:3.14-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates gosu gettext-base nginx \
      mariadb-client libmariadb3 \
      wkhtmltopdf fonts-dejavu-core fonts-liberation \
      libjpeg62-turbo libffi8 libssl3 zlib1g libstdc++6 \
      libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 shared-mime-info \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default
RUN pip install --no-cache-dir frappe-bench==5.31.1
# Frappe v16 realtime uses the node backend (no frappe.realtime.server), so the
# runtime image carries the same Node 24 binary used to build assets.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN useradd -m -u 1000 frappe
COPY --from=builder /home/frappe/frappe-bench /home/frappe/frappe-bench
RUN cp -a /home/frappe/frappe-bench/sites/assets /opt/seed-assets \
 && cp /home/frappe/frappe-bench/sites/apps.txt /opt/seed-apps.txt \
 && sha256sum /opt/seed-assets/assets.json | cut -d' ' -f1 > /opt/assets.sha
COPY deploy/vps/entrypoint.sh /opt/entrypoint.sh
COPY deploy/vps/setup.sh /opt/setup.sh
COPY deploy/vps/backup.sh /opt/backup.sh
COPY deploy/vps/restore.sh /opt/restore.sh
COPY deploy/vps/frontend/ /opt/frontend/
RUN chmod +x /opt/entrypoint.sh /opt/setup.sh /opt/backup.sh /opt/restore.sh /opt/frontend/entrypoint.sh
ENV HOME=/home/frappe \
    PATH=/home/frappe/frappe-bench/env/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /home/frappe/frappe-bench
ENTRYPOINT ["/opt/entrypoint.sh"]
