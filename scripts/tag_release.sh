#!/usr/bin/env bash
# Crée un tag de release et le pousse vers Gitea (déclenche le workflow release.yml).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION_FILE="$ROOT/VERSION"
CURRENT="$(tr -d ' \n' < "$VERSION_FILE")"
NEXT="${1:-}"

if [[ -z "$NEXT" ]]; then
  echo "Usage: $0 <version>   ex. $0 1.0.1  → tag v1.0.1"
  echo "Version actuelle : $CURRENT"
  exit 1
fi

TAG="v${NEXT}"

if ! grep -q "^## \\[${NEXT}\\]" CHANGELOG.md 2>/dev/null; then
  echo "Attention : aucune section ## [${NEXT}] dans CHANGELOG.md"
fi

echo "$NEXT" > "$VERSION_FILE"
python3 scripts/sync_asset_version.py

git add VERSION CHANGELOG.md index.html
git commit -m "chore: release ${TAG}" || true
git tag -a "$TAG" -m "Lab Console ${TAG}"
git push origin HEAD
git push origin "$TAG"

echo "Tag ${TAG} poussé — le workflow « Release et déploiement » va s'exécuter."
