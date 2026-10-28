#!/bin/bash
set -euo pipefail
: "${SITE_NAME:?SITE_NAME is required}"
envsubst '${SITE_NAME}' < /opt/frontend/default.conf.template > /etc/nginx/conf.d/payroll.conf
rm -f /etc/nginx/sites-enabled/default
exec nginx -g 'daemon off;'
