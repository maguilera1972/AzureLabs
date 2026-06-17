# Déploiement et CI/CD Gitea — Lab Console

Ce dossier contient tout le nécessaire pour déployer Lab Console et automatiser les mises à jour via [Gitea Actions](https://docs.gitea.com/usage/actions/overview).

**Dépôt :** https://git.aguilera.ch/Michel/AzureLabs

## Fichiers

| Fichier | Rôle |
|---------|------|
| `install.sh` | Installation initiale (clone, venv, systemd, nginx) |
| `deploy.sh` | Mise à jour en production (git pull/tag, pip, restart API) |
| `regenerate-content.sh` | Régénère le mode d'emploi PDF/Word |
| `lab-console-api.service` | Unité systemd |
| `nginx-lab-console.conf` | Configuration nginx |

## Workflows Gitea (`.gitea/workflows/`)

| Workflow | Déclencheur | Action |
|----------|-------------|--------|
| **CI** | Push / PR sur `main` | Vérifie syntaxe Python et imports FastAPI |
| **Contenu** | Push sur `js/`, `css/`, scripts manuel **ou** manuel | Régénère PDF/Word ; option captures Playwright |
| **Release** | Tag `v*` (ex. `v1.0.1`) | Déploie en prod, crée release Gitea + PDF joint |

## Prérequis Gitea

### 1. Activer Actions sur le dépôt

Dans Gitea → **Michel/AzureLabs** → **Paramètres** → cocher **Activer les Actions**.

### 2. Installer un runner (`act_runner`)

Sur le serveur `azurelabs` (recommandé, mode host) :

```bash
# Télécharger act_runner (adapter la version à votre Gitea)
curl -sL https://gitea.com/gitea/act_runner/releases/latest/download/act_runner-linux-amd64 -o /usr/local/bin/act_runner
chmod +x /usr/local/bin/act_runner

# Token : Gitea → Paramètres du dépôt → Actions → Runners → Créer un token
act_runner register \
  --instance https://git.aguilera.ch \
  --token <TOKEN_RUNNER> \
  --name azurelabs-runner \
  --labels self-hosted:host

# Service systemd (exemple)
cat > /etc/systemd/system/gitea-act-runner.service <<'EOF'
[Unit]
Description=Gitea Actions Runner
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/lab-console
ExecStart=/usr/local/bin/act_runner daemon
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now gitea-act-runner
```

Le label `self-hosted` est requis par les workflows.

### 3. Secret `GITEA_TOKEN`

Pour créer les releases automatiquement :

1. Gitea → **Paramètres utilisateur** → **Applications** → générer un token (scope `write:repository`)
2. Dépôt → **Paramètres** → **Secrets** → ajouter `GITEA_TOKEN`

## Premier déploiement

```bash
# Sur le serveur (déjà en place si vous lisez ceci depuis /var/www/lab-console)
cd /var/www/lab-console
git remote add origin https://git.aguilera.ch/Michel/AzureLabs.git
git push -u origin main
```

Si le dépôt Gitea est vide, la première poussée initialise la branche `main`.

## Mise à jour manuelle

```bash
cd /var/www/lab-console
./deploy/deploy.sh main
```

## Publier une release

1. Mettre à jour `CHANGELOG.md` (section `## [x.y.z]`)
2. Lancer :

```bash
./scripts/tag_release.sh 1.0.1
```

Cela met à jour `VERSION`, crée le tag `v1.0.1`, pousse vers Gitea et déclenche :
- déploiement sur `/var/www/lab-console`
- création de la release avec le PDF du mode d'emploi en pièce jointe

## Régénérer le mode d'emploi

```bash
# PDF/Word uniquement (captures existantes)
./deploy/regenerate-content.sh

# Avec nouvelles captures d'écran (API + nginx doivent tourner)
CAPTURE_SCREENSHOTS=true ./deploy/regenerate-content.sh
```

Ou via Gitea → **Actions** → **Contenu — mode d'emploi** → **Run workflow**.

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `LAB_CONSOLE_HOME` | `/var/www/lab-console` | Répertoire d'installation |
| `LAB_CONSOLE_SERVICE` | `lab-console-api` | Nom du service systemd |
| `DEPLOY_REF` | `origin/main` | Référence git à déployer |
| `CAPTURE_SCREENSHOTS` | `false` | Active Playwright pour les captures |

## Fichiers exclus du dépôt

- `backend/.env` — secrets (copier depuis `.env.example`)
- `data/*` — base SQLite, logos uploadés, credentials chiffrés
- `venv/` — environnement Python local
