#!/usr/bin/env bash
# Installation initiale de Lab Console sur un serveur Debian/Ubuntu.
set -euo pipefail

APP_DIR="${LAB_CONSOLE_HOME:-/var/www/lab-console}"
REPO_URL="${GITEA_REPO_URL:-https://git.aguilera.ch/Michel/AzureLabs.git}"

log() { echo "[install] $*"; }

if [[ $EUID -ne 0 ]]; then
  echo "Exécutez ce script en root (sudo)." >&2
  exit 1
fi

apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx git rsync

if [[ ! -d "$APP_DIR/.git" ]]; then
  log "Clonage du dépôt…"
  git clone "$REPO_URL" "$APP_DIR"
else
  log "Dépôt déjà présent dans $APP_DIR"
fi

cd "$APP_DIR"
chmod +x deploy/deploy.sh deploy/regenerate-content.sh

if [[ ! -f backend/.env ]]; then
  cp backend/.env.example backend/.env
  log "backend/.env créé depuis .env.example — adaptez SECRET_KEY avant la production"
fi

python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r backend/requirements.txt

mkdir -p data/branding
chown -R www-data:www-data data

cp deploy/lab-console-api.service /etc/systemd/system/lab-console-api.service
cp deploy/nginx-lab-console.conf /etc/nginx/sites-available/lab-console
ln -sf /etc/nginx/sites-available/lab-console /etc/nginx/sites-enabled/lab-console
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

systemctl daemon-reload
systemctl enable lab-console-api
systemctl restart lab-console-api
nginx -t && systemctl reload nginx

log "Installation terminée — https://azurelabs.aguilera.ch"
