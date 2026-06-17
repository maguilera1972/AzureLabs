#!/usr/bin/env bash
# Déploie Lab Console sur le serveur de production (même machine ou via runner Gitea).
set -euo pipefail

APP_DIR="${LAB_CONSOLE_HOME:-/var/www/lab-console}"
REF="${DEPLOY_REF:-${1:-origin/main}}"
REF="${REF#refs/tags/}"
REF="${REF#refs/heads/}"
VENV="${APP_DIR}/venv"
SERVICE="${LAB_CONSOLE_SERVICE:-lab-console-api}"

log() { echo "[deploy] $*"; }

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "Erreur : $APP_DIR n'est pas un dépôt git" >&2
  exit 1
fi

cd "$APP_DIR"

log "Récupération de $REF…"
git fetch origin --tags
if git rev-parse --verify --quiet "refs/tags/${REF}" >/dev/null 2>&1; then
  git checkout "$REF"
elif git show-ref --verify --quiet "refs/remotes/origin/${REF}" 2>/dev/null; then
  git checkout -B deploy-tmp "origin/${REF}"
else
  git checkout "$REF"
fi

if [[ ! -d "$VENV" ]]; then
  log "Création du virtualenv…"
  python3 -m venv "$VENV"
fi

log "Installation des dépendances Python…"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r backend/requirements.txt

if [[ -f scripts/sync_asset_version.py ]]; then
  log "Synchronisation des versions d'assets…"
  "$VENV/bin/python3" scripts/sync_asset_version.py || true
fi

chown -R www-data:www-data "$APP_DIR/data" 2>/dev/null || true
chmod 755 "$APP_DIR/data" "$APP_DIR/data/branding" 2>/dev/null || true

if systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
  log "Redémarrage de $SERVICE…"
  systemctl restart "$SERVICE"
elif systemctl list-unit-files | grep -q "^${SERVICE}.service"; then
  log "Démarrage de $SERVICE…"
  systemctl enable --now "$SERVICE"
else
  log "Service systemd $SERVICE introuvable — ignoré"
fi

if command -v nginx >/dev/null && nginx -t 2>/dev/null; then
  systemctl reload nginx 2>/dev/null || true
fi

VERSION="$(cat VERSION 2>/dev/null || echo unknown)"
log "Déploiement terminé — Lab Console v${VERSION}"
