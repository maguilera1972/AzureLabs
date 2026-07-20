#!/usr/bin/env bash
# Commit local changes (if any) and push to Gitea origin/main.
# Usage: ./scripts/push_to_gitea.sh ["commit message"]
# No secrets in this script. Prefer SSH; HTTP fallback needs GITEA_TOKEN in env.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_SSH="git@172.16.12.12:Aguilera_lab/AzureLabs.git"
REMOTE_HTTP="http://172.16.12.12:3000/Aguilera_Lab/AzureLabs.git"
BRANCH="main"

git_cmd() {
  GIT_CONFIG_GLOBAL=/dev/null git -c "safe.directory=${REPO_ROOT}" -C "${REPO_ROOT}" "$@"
}

MSG="${1:-chore: sync lab-console changes}"

# Ensure origin points at the expected Gitea repo
if ! git_cmd remote get-url origin >/dev/null 2>&1; then
  git_cmd remote add origin "${REMOTE_SSH}"
else
  CURRENT="$(git_cmd remote get-url origin)"
  if [[ "${CURRENT}" != *"Aguilera_lab/AzureLabs"* && "${CURRENT}" != *"Aguilera_Lab/AzureLabs"* ]]; then
    echo "Fixing origin: ${CURRENT} -> ${REMOTE_SSH}"
    git_cmd remote set-url origin "${REMOTE_SSH}"
  fi
fi

# Nothing to do if working tree is clean and nothing to push
if git_cmd diff --quiet && git_cmd diff --cached --quiet; then
  UNTRACKED="$(git_cmd ls-files --others --exclude-standard)"
  if [[ -z "${UNTRACKED}" ]]; then
    # Still push if ahead of remote
    if git_cmd rev-parse --abbrev-ref "@{u}" >/dev/null 2>&1; then
      AHEAD="$(git_cmd rev-list --count "@{u}..HEAD" 2>/dev/null || echo 0)"
      if [[ "${AHEAD}" == "0" ]]; then
        echo "No local changes and branch is up to date."
        exit 0
      fi
    fi
  fi
fi

# Stage everything except secrets / local data
git_cmd add -A
git_cmd reset -- backend/.env 2>/dev/null || true
# Unstage anything under data/ (runtime / local)
while IFS= read -r -d '' f; do
  git_cmd reset -- "$f" 2>/dev/null || true
done < <(git_cmd diff --cached --name-only -z -- 'data/' 2>/dev/null || true)

# Drop common secret patterns from the index if staged
for pat in '*.pem' '*.key' '*credentials*' '*secret*' '*token*' '.env' '.env.*'; do
  while IFS= read -r f; do
    [[ -n "$f" ]] && git_cmd reset -- "$f" 2>/dev/null || true
  done < <(git_cmd diff --cached --name-only -- "$pat" 2>/dev/null || true)
done

if git_cmd diff --cached --quiet; then
  echo "Nothing staged to commit (secrets/data excluded or no changes)."
else
  git_cmd commit -m "$(cat <<EOF
${MSG}

EOF
)"
fi

HASH="$(git_cmd rev-parse --short HEAD)"

push_ssh() {
  git_cmd push -u origin "${BRANCH}"
}

push_http() {
  if [[ -z "${GITEA_TOKEN:-}" ]]; then
    echo "SSH push failed and GITEA_TOKEN is not set."
    echo "Export GITEA_TOKEN (Gitea personal access token) and re-run, or fix SSH keys."
    return 1
  fi
  # Ephemeral remote URL with token; never written to disk config permanently
  local url="http://oauth2:${GITEA_TOKEN}@172.16.12.12:3000/Aguilera_Lab/AzureLabs.git"
  git_cmd push "${url}" "HEAD:refs/heads/${BRANCH}"
}

if push_ssh 2>/tmp/lab-console-push-err.$$; then
  echo "Pushed ${HASH} to Gitea Aguilera_lab/AzureLabs (${BRANCH}) via SSH."
  rm -f /tmp/lab-console-push-err.$$
  exit 0
fi

echo "SSH push failed; trying HTTP with GITEA_TOKEN from environment..."
cat /tmp/lab-console-push-err.$$ >&2 || true
rm -f /tmp/lab-console-push-err.$$

if push_http; then
  echo "Pushed ${HASH} to Gitea Aguilera_lab/AzureLabs (${BRANCH}) via HTTP."
  exit 0
fi

echo "Push failed. Commit may exist locally as ${HASH}."
exit 1
