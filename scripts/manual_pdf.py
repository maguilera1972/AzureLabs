"""Génère le mode d'emploi Lab Console au format PDF."""

from __future__ import annotations

import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from manual_shared import MAIN_FEATURES, MANUAL_TOC, SCREENSHOT_GALLERY  # noqa: E402
from app.azure.pdf_branding import (  # noqa: E402
    BRAND_BORDER,
    BRAND_MUTED,
    BRAND_PURPLE,
    BRAND_TEXT,
    get_logo_path,
    page_callbacks,
)

SCREENSHOTS_DIR = ROOT / "docs" / "screenshots"
OUTPUT_PATH = ROOT / "docs" / "Mode-emploi-Lab-Console.pdf"

CONTENT_WIDTH = A4[0] - 4 * cm


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "ManualH1", parent=base["Heading1"], fontSize=16, leading=20,
            textColor=BRAND_PURPLE, spaceBefore=14, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "ManualH2", parent=base["Heading2"], fontSize=12, leading=15,
            textColor=BRAND_TEXT, spaceBefore=10, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "ManualBody", parent=base["Normal"], fontSize=10, leading=14,
            textColor=BRAND_TEXT, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "ManualBullet", parent=base["Normal"], fontSize=10, leading=14,
            textColor=BRAND_TEXT, leftIndent=14, bulletIndent=0, spaceAfter=3,
        ),
        "numbered": ParagraphStyle(
            "ManualNumbered", parent=base["Normal"], fontSize=10, leading=14,
            textColor=BRAND_TEXT, leftIndent=14, spaceAfter=3,
        ),
        "note": ParagraphStyle(
            "ManualNote", parent=base["Normal"], fontSize=9, leading=12,
            textColor=BRAND_MUTED, leftIndent=10, spaceAfter=6,
        ),
        "caption": ParagraphStyle(
            "ManualCaption", parent=base["Normal"], fontSize=8, leading=10,
            textColor=BRAND_MUTED, alignment=TA_CENTER, spaceAfter=10,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle", parent=base["Title"], fontSize=26, leading=30,
            textColor=BRAND_TEXT, alignment=TA_CENTER, spaceAfter=8,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub", parent=base["Normal"], fontSize=13, leading=16,
            textColor=BRAND_MUTED, alignment=TA_CENTER, spaceAfter=4,
        ),
        "center": ParagraphStyle(
            "ManualCenter", parent=base["Normal"], fontSize=10, leading=14,
            textColor=BRAND_MUTED, alignment=TA_CENTER, spaceAfter=6,
        ),
    }


def _para(story, text, style):
    story.append(Paragraph(text, style))


def _h1(story, styles, text):
    _para(story, text, styles["h1"])


def _h2(story, styles, text):
    _para(story, text, styles["h2"])


def _body(story, styles, text):
    _para(story, text, styles["body"])


def _bullets(story, styles, items):
    for item in items:
        _para(story, f"• {item}", styles["bullet"])


def _numbered(story, styles, items):
    for i, item in enumerate(items, 1):
        _para(story, f"{i}. {item}", styles["numbered"])


def _note(story, styles, text):
    _para(story, f"<b>Note :</b> {text}", styles["note"])


def _table(story, headers, rows):
    data = [headers] + [[str(c) for c in row] for row in rows]
    col_count = len(headers)
    col_w = CONTENT_WIDTH / col_count
    table = Table(data, colWidths=[col_w] * col_count, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4fa")),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_TEXT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.3 * cm))


def _screenshot(story, styles, filename: str, caption: str) -> int:
    path = SCREENSHOTS_DIR / filename
    if not path.exists():
        _para(story, f"<i>[Capture non disponible : {filename}]</i>", styles["note"])
        return 0

    img = Image.open(path)
    if img.mode in ("RGBA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    max_w_px = 1200
    if img.width > max_w_px:
        ratio = max_w_px / img.width
        img = img.resize((max_w_px, int(img.height * ratio)), Image.Resampling.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)

    display_w = CONTENT_WIDTH
    display_h = display_w * img.height / img.width
    max_h = 18 * cm
    if display_h > max_h:
        display_h = max_h
        display_w = display_h * img.width / img.height

    story.append(RLImage(buf, width=display_w, height=display_h))
    _para(story, caption, styles["caption"])
    return 1


def build_manual_pdf(output_path: Path | None = None) -> Path:
    output_path = output_path or OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=3.6 * cm,
        bottomMargin=2.2 * cm,
        title="Mode d'emploi — Lab Console",
    )
    styles = _styles()
    story = []
    version_date = datetime.now().strftime("%d/%m/%Y")

    if get_logo_path().exists():
        logo = RLImage(str(get_logo_path()), width=3 * cm, height=3 * cm)
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 0.8 * cm))

    _para(story, "Lab Console", styles["cover_title"])
    _para(story, "Mode d'emploi — Azure Training Labs", styles["cover_sub"])
    _para(story, f"Version du document : {version_date}", styles["center"])
    _para(story, "Console web de gestion d'ateliers de formation Azure", styles["center"])
    story.append(PageBreak())

    _h1(story, styles, "Sommaire")
    _bullets(story, styles, MANUAL_TOC)
    story.append(PageBreak())

    _h1(story, styles, "1. Présentation")
    _body(story, styles,
          "Lab Console est une interface web permettant de provisionner, piloter et suivre des ateliers "
          "de formation sur Microsoft Azure. Chaque atelier correspond à un groupe de ressources Azure "
          "dédié contenant des machines virtuelles (VM), une planification de démarrage/arrêt et des "
          "identifiants de connexion uniques par participant.")
    _body(story, styles, "Fonctionnalités principales :")
    _bullets(story, styles, MAIN_FEATURES)

    _h1(story, styles, "2. Aperçu visuel de l'interface")
    _body(story, styles,
          "Cette section présente les principaux écrans de Lab Console. Chaque capture illustre "
          "ce que vous verrez dans la console de gestion des ateliers.")
    embedded = 0
    for idx, (filename, title, description) in enumerate(SCREENSHOT_GALLERY, 1):
        _h2(story, styles, f"2.{idx} {title}")
        _body(story, styles, description)
        embedded += _screenshot(story, styles, filename, f"Figure {idx} — {title}")
        if idx < len(SCREENSHOT_GALLERY):
            story.append(PageBreak())
    print(f"Captures intégrées dans le PDF : {embedded}/{len(SCREENSHOT_GALLERY)}")

    _h1(story, styles, "3. Accès et connexion à la console")
    _body(story, styles,
          "Ouvrez un navigateur web moderne (Chrome, Edge, Firefox) et accédez à l'URL de la console, "
          "par exemple : https://azurelabs.aguilera.ch")
    _h2(story, styles, "3.1 Authentification")
    _body(story, styles,
          "L'accès à Lab Console est protégé par identifiant et mot de passe. À l'ouverture de l'URL, "
          "l'écran de connexion s'affiche (voir figure 1).")
    _numbered(story, styles, [
        "Saisir votre identifiant et mot de passe",
        "Cliquer sur Se connecter",
        "À la première connexion, changer le mot de passe si demandé",
    ])
    _note(story, styles,
          "Les nouveaux comptes reçoivent le mot de passe initial « welcome » et doivent le modifier immédiatement.")
    _h2(story, styles, "3.2 Interface après connexion")
    _body(story, styles, "L'interface est organisée en quatre zones :")
    _bullets(story, styles, [
        "Barre latérale gauche : navigation entre les sections",
        "Zone principale : contenu et formulaires",
        "Barre supérieure : profil utilisateur (avatar Gravatar, nom, déconnexion)",
        "Barre supérieure : bascule CHF/EUR, taux de change et horloge",
    ])

    _h1(story, styles, "4. Gestion des utilisateurs")
    _body(story, styles,
          "La section Utilisateurs (menu Configuration) est réservée aux administrateurs "
          "(voir figure 8).")
    _h2(story, styles, "4.1 Création d'un utilisateur")
    _table(story, ["Champ", "Description"], [
        ["Identifiant", "Nom de connexion unique"],
        ["Prénom / Nom", "Affichés dans la console et sur les ateliers"],
        ["Adresse e-mail", "Utilisée pour l'avatar Gravatar"],
    ])
    _note(story, styles, "Le mot de passe initial est « welcome ».")
    _h2(story, styles, "4.2 Modification et suppression")
    _bullets(story, styles, [
        "Modifier : prénom, nom, e-mail, rôle et mot de passe",
        "Réinit. MDP : remet le mot de passe à « welcome »",
        "Désactiver / Activer : bloque ou rétablit l'accès",
        "Supprimer : suppression définitive du compte",
    ])
    _note(story, styles,
          "Tous les utilisateurs peuvent provisionner des ateliers. Chaque atelier affiche son auteur.")

    _h1(story, styles, "5. Connexion Azure")
    _h2(story, styles, "5.1 Prérequis Azure AD")
    _body(story, styles,
          "Une application Azure AD dédiée est requise (le client Azure CLI est bloqué par les politiques "
          "Conditional Access). Créez une inscription d'application de type « Web » avec :")
    _bullets(story, styles, [
        "Permission API : Azure Service Management → user_impersonation",
        "Permission optionnelle : Microsoft Graph → Organization.Read.All",
        "URI de redirection : https://&lt;votre-domaine&gt;/api/azure/auth/callback",
        "Client Secret (colonne Valeur, pas l'ID du secret)",
    ])
    _h2(story, styles, "5.2 Configuration dans la console")
    _numbered(story, styles, [
        "Menu Configuration → Connexion Azure",
        "Saisir le Client ID, le Tenant ID (recommandé) et le Client Secret",
        "Cliquer sur Enregistrer la configuration",
        "Cliquer sur Se connecter avec Microsoft",
        "S'authentifier (MFA si activée) — message « Étape 1/2 réussie »",
        "Sélectionner la souscription de facturation",
        "Cliquer sur Utiliser cet environnement — badge Azure vert",
    ])
    _note(story, styles, "Le compte doit disposer du rôle Contributor sur la souscription cible. Voir figure 6.")

    _h1(story, styles, "6. Tableau de bord")
    _body(story, styles, "Le tableau de bord affiche une vue consolidée de tous les ateliers :")
    _bullets(story, styles, [
        "Nombre d'ateliers, VMs totales, VMs en cours d'exécution",
        "vCPU et RAM agrégés",
        "Coût estimé total (CHF ou EUR selon la devise active)",
        "Tableau détaillé par atelier avec lien vers le détail (voir figure 2)",
    ])

    _h1(story, styles, "7. Création d'un atelier")
    _h2(story, styles, "7.1 Informations générales")
    _table(story, ["Champ", "Description"], [
        ["Nom de l'atelier", "Identifiant lisible (ex. Formation-Docker-Mars)"],
        ["Région Azure", "francecentral, westeurope, northeurope, switzerlandnorth"],
        ["Durée", "Nombre de jours pour le calcul des coûts (1 à 365)"],
    ])
    _h2(story, styles, "7.2 Planification automatique")
    _body(story, styles,
          "Par défaut, les VMs démarrent à 7h et s'arrêtent à 19h (fuseau Europe/Paris). "
          "La planification peut être désactivée pour un pilotage manuel.")
    _h2(story, styles, "7.3 Configuration des VMs")
    _body(story, styles, "Pour chaque ligne de configuration :")
    _table(story, ["Champ", "Description"], [
        ["Préfixe de nom", "Base du nom des VMs (ex. win11 → win11-01, win11-02…)"],
        ["Système d'exploitation", "Windows 11, Windows Server 2025 ou Ubuntu"],
        ["Quantité", "Nombre de VMs à créer (1 à 100)"],
        ["Taille VM", "Standard_D4s_v3 par défaut (virtualisation imbriquée)"],
        ["Utilisateur / Mot de passe", "Optionnels — générés automatiquement si vides"],
    ])
    _h2(story, styles, "7.4 Estimation et création")
    _numbered(story, styles, [
        "L'estimation de consommation s'affiche automatiquement",
        "Optionnel : Générer l'offre PDF avant création",
        "Cliquer sur Créer l'atelier",
        "Les identifiants sont générés immédiatement, avant le déploiement Azure",
        "Le statut passe à « création en cours » avec suivi VM par VM (voir figure 7)",
    ])
    _note(story, styles, "L'atelier est associé à votre compte utilisateur.")

    _h1(story, styles, "8. Gestion d'un atelier")
    _body(story, styles, "Depuis Ateliers, cliquez sur une carte pour ouvrir le détail (voir figure 3).")
    _h2(story, styles, "8.1 Statuts")
    _table(story, ["Statut", "Signification"], [
        ["création en cours", "Provisionnement Azure en cours"],
        ["prêt", "Toutes les VMs sont opérationnelles"],
        ["suppression en cours", "Groupe de ressources en cours de suppression"],
        ["erreur", "Échec du provisionnement — supprimer et recréer"],
    ])
    _h2(story, styles, "8.2 Actions disponibles")
    _bullets(story, styles, [
        "Rafraîchir : met à jour le statut (auto toutes les 8 s pendant création/suppression)",
        "Exporter PDF : identifiants de connexion de toutes les VMs",
        "Supprimer l'atelier : lance la suppression du groupe de ressources Azure",
        "Copier le mot de passe : sur chaque carte VM",
    ])
    _h2(story, styles, "8.3 Suivi du provisionnement")
    _body(story, styles,
          "Pendant la création, chaque VM affiche un statut : En attente → Création Azure… → running. "
          "Le compteur indique X / Y VM(s) prête(s). Les identifiants et mots de passe sont visibles "
          "dès le début, avant l'attribution des adresses IP.")

    _h1(story, styles, "9. Estimation des coûts et offre PDF")
    _body(story, styles, "Menu Estimation coûts — permet d'anticiper les coûts sans créer d'atelier.")
    _numbered(story, styles, [
        "Renseigner le nom de l'atelier et le client (optionnel)",
        "Choisir la région, la durée et la planification horaire",
        "Ajouter les configurations VM",
        "Calculer l'estimation",
        "Générer l'offre PDF",
    ])
    _note(story, styles,
          "L'offre PDF inclut le logo, le détail des coûts, le taux de change et une validité de 30 jours. Voir figure 5.")

    _h1(story, styles, "10. Documents PDF")
    _table(story, ["Document", "Quand", "Contenu"], [
        ["Offre commerciale", "Avant ou pendant la création", "Coûts, configuration, conditions"],
        ["Identifiants de connexion", "Dès que les VMs sont enregistrées", "Utilisateur, mot de passe, IP, commande RDP/SSH"],
    ])
    _note(story, styles, "Réexportez le PDF identifiants une fois toutes les IP assignées.")

    _h1(story, styles, "11. Gestion des machines virtuelles")
    _body(story, styles, "Sur une VM en statut prêt :")
    _bullets(story, styles, [
        "Démarrer / Arrêter : contrôle manuel de l'alimentation",
        "Identifiants : fenêtre modale avec détails de connexion",
    ])
    _body(story, styles, "Accès distant :")
    _bullets(story, styles, [
        "Windows : RDP (port 3389) — mstsc /v:&lt;IP&gt;",
        "Ubuntu : SSH (port 22) — ssh &lt;utilisateur&gt;@&lt;IP&gt;",
    ])

    _h1(story, styles, "12. Planification automatique")
    _body(story, styles,
          "Si activée à la création, Azure Automation provisionne des runbooks Start-LabVMs et Stop-LabVMs "
          "dans le groupe de ressources. Les VMs démarrent et s'arrêtent selon le créneau configuré.")

    _h1(story, styles, "13. Suppression d'un atelier")
    _numbered(story, styles, [
        "Cliquer sur Supprimer l'atelier et confirmer",
        "Le statut passe à « suppression en cours »",
        "Rafraîchir pour suivre — redirection automatique quand Azure a terminé",
    ])
    _note(story, styles,
          "Si le groupe de ressources a été supprimé manuellement dans le portail Azure, "
          "un rafraîchissement finalise la suppression en base.")

    _h1(story, styles, "14. Devise et taux de change")
    _body(story, styles,
          "La console affiche les coûts en CHF par défaut. Le bouton CHF/EUR dans la barre supérieure "
          "bascule l'affichage. Le taux EUR/CHF est mis à jour automatiquement toutes les heures.")

    _h1(story, styles, "15. Dépannage")
    _table(story, ["Problème", "Solution"], [
        ["Session expirée", "Se reconnecter"],
        ["Mot de passe à changer", "Modifier le mot de passe à la première connexion"],
        ["Accès refusé à Utilisateurs", "Réservé aux administrateurs"],
        ["Badge Azure « Non connecté »", "Compléter l'étape 2 : choisir une souscription"],
        ["Erreur Conditional Access", "Utiliser l'application Azure AD dédiée"],
        ["Erreur AADSTS7000218", "Vérifier le Client Secret"],
        ["Provisionnement bloqué", "Rafraîchir, vérifier quotas, supprimer et recréer"],
        ["Suppression bloquée", "Rafraîchir — détection auto si RG supprimé"],
        ["PDF sans IP", "Attendre la fin du provisionnement et réexporter"],
    ])

    _h1(story, styles, "16. Bonnes pratiques de sécurité")
    _bullets(story, styles, [
        "Restreindre l'accès réseau à la console (VPN, pare-feu)",
        "Créer un compte par formateur — éviter le partage des identifiants",
        "Désactiver ou supprimer les comptes inutilisés",
        "Ne pas diffuser les PDF d'identifiants en dehors des participants",
        "Changer SECRET_KEY en production",
        "Restreindre les NSG (RDP/SSH) à des plages IP connues en production",
        "Supprimer les ateliers en fin de formation pour limiter les coûts",
        "Surveiller le tableau de bord pour détecter les VMs oubliées en marche",
    ])

    story.append(Spacer(1, 0.5 * cm))
    _para(story, "<i>— Fin du document —</i>", styles["center"])

    doc.build(story, onFirstPage=page_callbacks("Mode d'emploi Lab Console"),
              onLaterPages=page_callbacks("Mode d'emploi Lab Console"))
    return output_path
