# Guide de déploiement — Lab Console

Ce document décrit l'installation complète de **Lab Console** sur un nouveau serveur Linux.

**Dépôt Gitea :** `git@172.16.12.12:Aguilera_lab/AzureLabs.git`  
**URL web Gitea :** http://172.16.12.12:3000/Aguilera_lab/AzureLabs

---

## 1. Prérequis

### Serveur

| Composant | Version minimale |
|-----------|------------------|
| OS | Debian 12 / Ubuntu 22.04+ |
| Python | 3.11+ |
| nginx | 1.18+ |
| git | 2.x |
| Accès réseau | HTTPS sortant (API Azure, taux de change) |

### Ressources recommandées

- **CPU :** 2 vCPU
- **RAM :** 2 Go
- **Disque :** 20 Go (`/var/www/lab-console` + logs)
- **Ports :** 80 (nginx), 8000 en local (API, non exposé)

### Azure

- Souscription Azure avec rôle **Contributor**
- Application Azure AD (type Web) pour l'authentification OAuth
- URI de redirection : `https://<votre-domaine>/api/azure/auth/callback`

---

## 2. Installation automatique (recommandée)

Connectez-vous au serveur cible en **root** ou avec `sudo` :

```bash
# Cloner le dépôt
export GITEA_REPO_URL=git@172.16.12.12:Aguilera_lab/AzureLabs.git
git clone "$GITEA_REPO_URL" /var/www/lab-console
cd /var/www/lab-console

# Lancer l'installation
chmod +x deploy/install.sh deploy/deploy.sh
./deploy/install.sh
```

Le script installe les paquets, crée le virtualenv Python, configure **systemd** et **nginx**.

---

## 3. Configuration post-installation

### 3.1 Fichier d'environnement

```bash
cp /var/www/lab-console/backend/.env.example /var/www/lab-console/backend/.env
nano /var/www/lab-console/backend/.env
```

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Clé Fernet 64 caractères — **obligatoire en production** |
| `DEFAULT_LOCATION` | Région Azure par défaut (`francecentral`) |
| `AZURE_PUBLIC_BASE_URL` | URL publique HTTPS de la console |

Générer une clé secrète :

```bash
/var/www/lab-console/venv/bin/python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3.2 Nom de domaine et nginx

Éditez `deploy/nginx-lab-console.conf` (ligne `server_name`) puis recopiez :

```bash
cp /var/www/lab-console/deploy/nginx-lab-console.conf /etc/nginx/sites-available/lab-console
nginx -t && systemctl reload nginx
```

### 3.3 HTTPS (optionnel — Cloudflare Tunnel)

Voir `deploy/cloudflared-config.yml.example` pour exposer la console sans ouvrir les ports 80/443.

### 3.4 Redémarrer l'API

```bash
systemctl restart lab-console-api
systemctl status lab-console-api
curl -s http://127.0.0.1:8000/api/health
```

---

## 4. Premier accès

1. Ouvrez `http://<adresse-du-serveur>/` dans un navigateur
2. Connectez-vous avec le compte administrateur par défaut (créé au premier démarrage) :
   - **Identifiant :** `admin`
   - **Mot de passe :** `admin` → **à changer immédiatement**
3. Menu **Configuration → Connexion Azure** : configurez l'application Azure AD
4. Créez des comptes utilisateurs si nécessaire (**Configuration → Utilisateurs**)

---

## 5. Mise à jour

```bash
cd /var/www/lab-console
./deploy/deploy.sh main
```

Ou via tag de release :

```bash
./scripts/tag_release.sh 1.1.0
```

---

## 6. Structure des répertoires

```
/var/www/lab-console/
├── index.html, css/, js/     # Interface web (servie par nginx)
├── backend/                  # API FastAPI
│   ├── app/
│   ├── requirements.txt
│   └── .env                  # Secrets (non versionné)
├── data/                     # SQLite + logos (non versionné)
├── deploy/                   # Scripts et configs serveur
├── docs/                     # Mode d'emploi PDF
└── venv/                     # Environnement Python
```

---

## 7. Services systemd

| Service | Fichier | Commande |
|---------|---------|----------|
| API | `deploy/lab-console-api.service` | `systemctl restart lab-console-api` |
| nginx | `/etc/nginx/sites-available/lab-console` | `systemctl reload nginx` |

---

## 8. CI/CD Gitea (optionnel)

Sur le serveur Gitea `172.16.12.12` :

1. Activer **Actions** sur le dépôt `Aguilera_lab/AzureLabs`
2. Installer `act_runner` sur le serveur de production (label `self-hosted`)
3. Ajouter le secret `GITEA_TOKEN` dans les paramètres du dépôt

Détails : [`deploy/README.md`](deploy/README.md)

---

## 9. Sauvegarde

À sauvegarder régulièrement :

| Chemin | Contenu |
|--------|---------|
| `/var/www/lab-console/data/lab_console.db` | Base SQLite (utilisateurs, ateliers, secrets chiffrés) |
| `/var/www/lab-console/backend/.env` | Clé de chiffrement |
| `/var/www/lab-console/data/branding/` | Logo personnalisé |

```bash
tar czf lab-console-backup-$(date +%Y%m%d).tar.gz \
  /var/www/lab-console/data \
  /var/www/lab-console/backend/.env
```

---

## 10. Dépannage

| Problème | Solution |
|----------|----------|
| API ne démarre pas | `journalctl -u lab-console-api -n 50` |
| Page blanche | Vérifier nginx : `nginx -t` |
| Erreur 502 | API arrêtée → `systemctl restart lab-console-api` |
| Azure non connecté | Vérifier Client ID, Secret, redirect URI |
| Permissions data | `chown -R www-data:www-data /var/www/lab-console/data` |

---

## 11. Checklist de déploiement

- [ ] Serveur provisionné (Debian/Ubuntu)
- [ ] Dépôt cloné depuis Gitea
- [ ] `./deploy/install.sh` exécuté sans erreur
- [ ] `SECRET_KEY` générée et renseignée dans `.env`
- [ ] `server_name` nginx adapté au domaine
- [ ] HTTPS configuré (reverse proxy ou Cloudflare Tunnel)
- [ ] Application Azure AD créée, redirect URI enregistré
- [ ] Connexion Azure testée dans la console
- [ ] Mot de passe `admin` changé
- [ ] Premier atelier de test créé et supprimé
- [ ] Sauvegarde `data/` planifiée
