# Lab Console — Azure Training Labs

Console web pour piloter la création et la gestion d'ateliers de formation sur Azure.

## Fonctionnalités

- **Connexion Azure** : authentification via Service Principal (Tenant ID, Client ID, Secret) avec choix de la souscription de facturation
- **Création d'ateliers** : chaque atelier = un groupe de ressources Azure dédié (`rg-lab-<nom>`)
- **Types de VM supportés** :
  - Windows 11 Enterprise (Gen2, Trusted Launch)
  - Windows Server 2025 Datacenter
  - Ubuntu Server 22.04 LTS
- **Virtualisation imbriquée** : tailles Dsv3/Dv3 (nested virtualization) pour WSL, Docker Desktop, Hyper-V
- **Accès distant** : RDP (Windows) et SSH (Ubuntu) avec IP publique individuelle par VM
- **Identifiants** : utilisateur et mot de passe personnalisés par VM
- **Planification** : démarrage/arrêt automatique (défaut 7h–19h) via Azure Automation
- **Estimation des coûts** : API Azure Retail Prices + calcul basé sur les heures d'utilisation
- **Tableau de bord** : métriques par atelier, groupe de ressources, vCPU, RAM, coûts
- **Suppression** : suppression complète d'un atelier (groupe de ressources + contenu) en une opération

## Architecture

```
/var/www/lab-console/
├── index.html          # Interface web (SPA)
├── css/style.css
├── js/
│   ├── api.js          # Client API
│   └── app.js          # Logique UI
├── backend/
│   ├── app/
│   │   ├── main.py     # FastAPI
│   │   ├── azure/      # Provisionnement, automation, coûts
│   │   └── routes/     # Endpoints REST
│   └── requirements.txt
├── data/               # Base SQLite (credentials chiffrés)
└── venv/               # Environnement Python
```

## Prérequis Azure

### Service Principal

Créez une application Azure AD avec les rôles suivantes sur la souscription cible :

- **Contributor** (création/suppression de ressources)
- **User Access Administrator** (optionnel, pour Automation RunAs)

```bash
az ad sp create-for-rbac --name "lab-console" --role Contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>
```

### Quotas

Vérifiez les quotas pour les tailles Dsv3 dans votre région (virtualisation imbriquée).

## Démarrage

```bash
# Service API
systemctl status lab-console-api
systemctl restart lab-console-api

# NGINX
nginx -t && systemctl reload nginx
```

Accès : `http://<hôte>/`

## API REST

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/health` | GET | Santé de l'API |
| `/api/azure/connect` | POST | Connexion Azure |
| `/api/azure/subscriptions` | GET | Liste des souscriptions |
| `/api/workshops` | GET/POST | Liste / création d'ateliers |
| `/api/workshops/{id}` | GET/DELETE | Détail / suppression |
| `/api/workshops/{id}/vms` | GET | VMs d'un atelier |
| `/api/workshops/estimate` | POST | Estimation des coûts |
| `/api/workshops/metrics/subscription` | GET | Métriques consolidées |
| `/api/vms/{ws}/{name}/start` | POST | Démarrer une VM |
| `/api/vms/{ws}/{name}/stop` | POST | Arrêter une VM |

## Configuration

Copiez et adaptez `backend/.env.example` vers `backend/.env` :

```env
SECRET_KEY=<clé-aléatoire-64-caractères>
DEFAULT_LOCATION=francecentral
DEFAULT_VM_SIZE=Standard_D4s_v3
```

## Sécurité

- Les secrets Azure et mots de passe VM sont chiffrés en base (Fernet)
- Changez `SECRET_KEY` en production
- Restreignez l'accès réseau à la console (VPN, IP allowlist)
- Les NSG autorisent RDP/SSH depuis `*` — restreignez en production

## Planification automatique

Lors de la création d'un atelier avec planification activée, un compte **Azure Automation** est provisionné dans le groupe de ressources avec :

- Runbook `Start-LabVMs` — démarrage quotidien
- Runbook `Stop-LabVMs` — arrêt quotidien
- Schedules configurables (heure + fuseau horaire)

> **Note** : le compte Automation nécessite une identité managée ou une connexion RunAs configurée. En cas d'échec à la création automatique, les runbooks sont créés mais la connexion RunAs devra être finalisée manuellement dans le portail Azure.

## Devise

- **CHF par défaut** : tous les coûts sont affichés en francs suisses
- **Bascule EUR** : bouton CHF/EUR dans la barre supérieure
- **Taux de change** : mis à jour automatiquement toutes les heures (sources : exchangerate-api.com, open.er-api.com, Frankfurter/BCE)
- Les prix Azure sont récupérés en EUR puis convertis en CHF via le taux du jour


L'estimation utilise l'[API Azure Retail Prices](https://prices.azure.com/api/retail/prices) et applique :

- Heures d'utilisation = fenêtre démarrage → arrêt
- Jours ouvrés par défaut : 22/mois
- Majoration ~40 % pour licences Windows
- Disques Premium 128 Go + IP publique Standard

Les coûts réels peuvent varier selon la région, les offres et la consommation effective.

## Dépôt Git et déploiement

- **Gitea :** `git@172.16.12.12:Michel/AI-Lab.git`
- **Guide d'installation :** [`DEPLOY.md`](DEPLOY.md)
- **Scripts serveur :** [`deploy/`](deploy/)

```bash
# Nouveau serveur
git clone git@172.16.12.12:Michel/AI-Lab.git /var/www/lab-console
cd /var/www/lab-console && sudo ./deploy/install.sh

# Mise à jour
./deploy/deploy.sh main
```
