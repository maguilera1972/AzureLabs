# Déploiement et CI/CD — Lab Console

**Dépôt :** `git@172.16.12.12:Aguilera_lab/AzureLabs.git`  
**Guide complet :** [`../DEPLOY.md`](../DEPLOY.md)

## Fichiers

| Fichier | Rôle |
|---------|------|
| `install.sh` | Installation initiale sur un nouveau serveur |
| `deploy.sh` | Mise à jour (git pull, pip, restart API) |
| `regenerate-content.sh` | Régénération du mode d'emploi PDF/Word |
| `lab-console-api.service` | Unité systemd de l'API |
| `nginx-lab-console.conf` | Configuration nginx |
| `cloudflared-config.yml.example` | Exemple Cloudflare Tunnel |

## Installation rapide

```bash
git clone git@172.16.12.12:Aguilera_lab/AzureLabs.git /var/www/lab-console
cd /var/www/lab-console
sudo ./deploy/install.sh
sudo nano /var/www/lab-console/backend/.env   # SECRET_KEY + URL publique
sudo systemctl restart lab-console-api
```

## Mise à jour

```bash
cd /var/www/lab-console
./deploy/deploy.sh main
```

## Workflows Gitea (`.gitea/workflows/`)

| Workflow | Déclencheur | Action |
|----------|-------------|--------|
| **CI** | Push / PR sur `main` | Vérifie Python + FastAPI |
| **Contenu** | Push UI ou manuel | Régénère le mode d'emploi |
| **Release** | Tag `v*` | Déploie + release Gitea |

### Runner Gitea (`act_runner`)

```bash
curl -sL https://gitea.com/gitea/act_runner/releases/latest/download/act_runner-linux-amd64 \
  -o /usr/local/bin/act_runner
chmod +x /usr/local/bin/act_runner

# Token : Gitea → Dépôt → Paramètres → Actions → Runners
act_runner register \
  --instance http://172.16.12.12 \
  --token <TOKEN_RUNNER> \
  --name lab-console-runner \
  --labels self-hosted:host

systemctl enable --now gitea-act-runner   # voir DEPLOY.md pour le unit file
```

### Secret `GITEA_TOKEN`

Gitea → Paramètres utilisateur → Applications → token (`write:repository`)  
Dépôt → Paramètres → Secrets → `GITEA_TOKEN`

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `LAB_CONSOLE_HOME` | `/var/www/lab-console` | Répertoire d'installation |
| `GITEA_REPO_URL` | `git@172.16.12.12:Aguilera_lab/AzureLabs.git` | URL du dépôt (install.sh) |
| `LAB_CONSOLE_SERVICE` | `lab-console-api` | Service systemd |
| `DEPLOY_REF` | `origin/main` | Référence git à déployer |

## Fichiers non versionnés

- `backend/.env` — secrets
- `data/*` — base SQLite, logos
- `venv/` — virtualenv Python
