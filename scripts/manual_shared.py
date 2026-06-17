"""Contenu partagé du mode d'emploi (Word + PDF)."""

SCREENSHOT_GALLERY = [
    ("00-connexion-console.png", "Connexion à la console",
     "Écran d'authentification : identifiant et mot de passe requis pour accéder à Lab Console."),
    ("01-tableau-de-bord.png", "Tableau de bord",
     "Vue d'ensemble après connexion : métriques consolidées, liste des ateliers et menu utilisateur (coin droit)."),
    ("02-ateliers.png", "Liste des ateliers",
     "Chaque carte affiche le nom, le groupe de ressources, la région, le statut, le coût et l'auteur du provisionnement."),
    ("03-nouvel-atelier.png", "Création d'un atelier",
     "Formulaire : nom, région, durée, planification horaire, configuration des VMs et estimation des coûts."),
    ("04-estimation-couts.png", "Estimation des coûts",
     "Simulation indépendante avec nom d'atelier, client, durée et bouton de génération d'offre PDF."),
    ("05-connexion-azure.png", "Connexion Azure",
     "Configuration Azure AD, authentification Microsoft (MFA) et choix de la souscription."),
    ("06-detail-atelier.png", "Détail d'un atelier",
     "Suivi du provisionnement, identifiants, auteur du provisionnement, Rafraîchir, Exporter PDF et Supprimer."),
    ("07-utilisateurs.png", "Gestion des utilisateurs",
     "Création, modification, réinitialisation de mot de passe et suppression des comptes (administrateurs)."),
]

MANUAL_TOC = [
    "1. Présentation",
    "2. Aperçu visuel de l'interface (captures d'écran)",
    "3. Accès et connexion à la console",
    "4. Gestion des utilisateurs",
    "5. Connexion Azure",
    "6. Tableau de bord",
    "7. Création d'un atelier",
    "8. Gestion d'un atelier",
    "9. Estimation des coûts et offre PDF",
    "10. Documents PDF",
    "11. Gestion des machines virtuelles",
    "12. Planification automatique",
    "13. Suppression d'un atelier",
    "14. Devise et taux de change",
    "15. Dépannage",
    "16. Bonnes pratiques de sécurité",
]

MAIN_FEATURES = [
    "Authentification console par identifiant et mot de passe",
    "Gestion des utilisateurs (création, modification, suppression)",
    "Traçabilité : affichage de l'auteur de chaque atelier provisionné",
    "Connexion Azure avec compte administrateur (MFA supportée)",
    "Création d'ateliers multi-VM (Windows 11, Windows Server 2025, Ubuntu)",
    "Virtualisation imbriquée (tailles Dsv3/Dv3/Dsv5)",
    "Génération automatique des identifiants avant provisionnement",
    "Export PDF des identifiants de connexion et des offres commerciales",
    "Estimation des coûts basée sur les tarifs publics Azure",
    "Tableau de bord consolidé (vCPU, RAM, coûts)",
    "Suppression complète d'un atelier (groupe de ressources Azure inclus)",
]
