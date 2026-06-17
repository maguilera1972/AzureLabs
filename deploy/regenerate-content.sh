#!/usr/bin/env bash
# Régénère le mode d'emploi (captures optionnelles + PDF + Word).
set -euo pipefail

APP_DIR="${LAB_CONSOLE_HOME:-/var/www/lab-console}"
CAPTURE="${CAPTURE_SCREENSHOTS:-false}"

cd "$APP_DIR"
VENV="${APP_DIR}/venv"

if [[ ! -x "$VENV/bin/python3" ]]; then
  echo "Virtualenv introuvable — lancez deploy/install.sh ou deploy/deploy.sh d'abord." >&2
  exit 1
fi

if [[ "$CAPTURE" == "true" ]]; then
  echo "[content] Installation Playwright (si nécessaire)…"
  "$VENV/bin/pip" install -q playwright
  "$VENV/bin/playwright" install chromium 2>/dev/null || "$VENV/bin/playwright" install-deps chromium

  echo "[content] Vérification de l'API…"
  if ! curl -sf http://127.0.0.1:8000/api/health >/dev/null; then
    systemctl restart lab-console-api 2>/dev/null || true
    sleep 2
  fi
  if ! curl -sf http://127.0.0.1:8000/api/health >/dev/null; then
    echo "L'API doit être accessible sur http://127.0.0.1:8000 pour les captures." >&2
    exit 1
  fi
fi

echo "[content] Génération du mode d'emploi…"
ARGS=()
if [[ "$CAPTURE" != "true" ]]; then
  ARGS+=(--no-capture)
fi
"$VENV/bin/python3" scripts/generate_manual.py "${ARGS[@]}"

"$VENV/bin/python3" scripts/sync_asset_version.py || true
echo "[content] Terminé."
