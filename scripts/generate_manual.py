#!/usr/bin/env python3
"""Génère le mode d'emploi Lab Console (PDF public, Word optionnel)."""

from datetime import datetime
from io import BytesIO
from pathlib import Path

import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manual_shared import MAIN_FEATURES, MANUAL_TOC, SCREENSHOT_GALLERY

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.branding import resolve_logo_path  # noqa: E402

LOGO_PATH = ROOT / "assets" / "logo.png"
SCREENSHOTS_DIR = ROOT / "docs" / "screenshots"
OUTPUT_PATH = ROOT / "docs" / "Mode-emploi-Lab-Console.docx"

BRAND_CYAN = RGBColor(0x56, 0xCC, 0xF2)
BRAND_PURPLE = RGBColor(0x8E, 0x2D, 0xE2)
BRAND_DARK = RGBColor(0x1A, 0x23, 0x32)
BRAND_MUTED = RGBColor(0x64, 0x74, 0x8B)


def _set_style_font(style, name="Calibri", size=11):
    style.font.name = name
    style.font.size = Pt(size)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def _heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        run.font.color.rgb = BRAND_PURPLE if level == 1 else BRAND_DARK
    return p


def _bullet(doc, text, level=0):
    p = doc.add_paragraph(text, style="List Bullet")
    if level:
        p.paragraph_format.left_indent = Cm(1.2 * level)
    return p


def _numbered(doc, text):
    return doc.add_paragraph(text, style="List Number")


def _note(doc, text):
    p = doc.add_paragraph()
    run = p.add_run("Note : ")
    run.bold = True
    run.font.color.rgb = BRAND_MUTED
    p.add_run(text)
    p.paragraph_format.left_indent = Cm(0.5)
    return p


def _screenshot(doc, filename: str, caption: str, width_cm: float = 17.0, page_break_after: bool = False):
    path = SCREENSHOTS_DIR / filename
    if not path.exists():
        print(f"ATTENTION: capture manquante — {path}")
        p = doc.add_paragraph(f"[Capture d'écran non disponible : {filename}]")
        for run in p.runs:
            run.font.color.rgb = BRAND_MUTED
            run.italic = True
        return 0

    img = Image.open(path)
    if img.mode in ("RGBA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    max_px = 1400
    if img.width > max_px:
        ratio = max_px / img.width
        img = img.resize((max_px, int(img.height * ratio)), Image.Resampling.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    buf.seek(0)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(buf, width=Cm(width_cm))

    cap = doc.add_paragraph(caption)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in cap.runs:
        run.italic = True
        run.font.size = Pt(9)
        run.font.color.rgb = BRAND_MUTED

    if page_break_after:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    else:
        doc.add_paragraph()

    return 1


def _table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = h
        for p in hdr[i].paragraphs:
            for r in p.runs:
                r.bold = True
    for ri, row in enumerate(rows):
        cells = table.rows[ri + 1].cells
        for ci, val in enumerate(row):
            cells[ci].text = str(val)
    doc.add_paragraph()
    return table


def build_manual() -> Document:
    doc = Document()
    for style_name in ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3"):
        if style_name in doc.styles:
            _set_style_font(doc.styles[style_name], size=11 if style_name == "Normal" else 14)

    # Page de garde
    if resolve_logo_path().exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(resolve_logo_path()), width=Cm(3.5))

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("Lab Console")
    run.bold = True
    run.font.size = Pt(28)
    run.font.color.rgb = BRAND_DARK

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run("Mode d'emploi — Azure Training Labs")
    r.font.size = Pt(16)
    r.font.color.rgb = BRAND_MUTED

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run(f"Version du document : {datetime.now().strftime('%d/%m/%Y')}\n").font.color.rgb = BRAND_MUTED
    meta.add_run("Console web de gestion d'ateliers de formation Azure").font.color.rgb = BRAND_MUTED

    doc.add_page_break()

    # Sommaire manuel
    _heading(doc, "Sommaire", 1)
    for item in MANUAL_TOC:
        _bullet(doc, item)
    doc.add_page_break()

    _heading(doc, "1. Présentation", 1)
    doc.add_paragraph(
        "Lab Console est une interface web permettant de provisionner, piloter et suivre des ateliers "
        "de formation sur Microsoft Azure. Chaque atelier correspond à un groupe de ressources Azure "
        "dédié contenant des machines virtuelles (VM), une planification de démarrage/arrêt et des "
        "identifiants de connexion uniques par participant."
    )
    doc.add_paragraph("Fonctionnalités principales :")
    for feat in MAIN_FEATURES:
        _bullet(doc, feat)

    _heading(doc, "2. Aperçu visuel de l'interface", 1)
    doc.add_paragraph(
        "Cette section présente les principaux écrans de Lab Console. Chaque capture illustre "
        "ce que vous verrez dans la console de gestion des ateliers. Les légendes décrivent "
        "les éléments clés de chaque vue."
    )
    embedded = 0
    for idx, (filename, title, description) in enumerate(SCREENSHOT_GALLERY, 1):
        _heading(doc, f"2.{idx} {title}", 2)
        doc.add_paragraph(description)
        embedded += _screenshot(
            doc,
            filename,
            f"Figure {idx} — {title}",
            width_cm=17.0,
            page_break_after=(idx < len(SCREENSHOT_GALLERY)),
        )
    print(f"Captures intégrées dans la galerie : {embedded}/{len(SCREENSHOT_GALLERY)}")

    _heading(doc, "3. Accès et connexion à la console", 1)
    doc.add_paragraph(
        "Ouvrez un navigateur web moderne (Chrome, Edge, Firefox) et accédez à l'URL de la console, "
        "par exemple : https://azurelabs.aguilera.ch"
    )
    _heading(doc, "3.1 Authentification", 2)
    doc.add_paragraph(
        "L'accès à Lab Console est protégé par identifiant et mot de passe. À l'ouverture de l'URL, "
        "l'écran de connexion s'affiche (voir capture 2.1)."
    )
    _numbered(doc, "Saisir votre identifiant et mot de passe")
    _numbered(doc, "Cliquer sur Se connecter")
    _numbered(doc, "À la première connexion, changer le mot de passe si demandé")
    _note(doc, "Les nouveaux comptes créés par un administrateur reçoivent le mot de passe initial « welcome » "
              "et doivent le modifier immédiatement.")

    _heading(doc, "3.2 Interface après connexion", 2)
    doc.add_paragraph("L'interface est organisée en quatre zones :")
    _bullet(doc, "Barre latérale gauche : navigation entre les sections")
    _bullet(doc, "Zone principale : contenu et formulaires")
    _bullet(doc, "Barre supérieure : profil utilisateur (avatar Gravatar, nom, déconnexion)")
    _bullet(doc, "Barre supérieure : bascule CHF/EUR, taux de change et horloge")

    _heading(doc, "4. Gestion des utilisateurs", 1)
    doc.add_paragraph(
        "La section Utilisateurs (menu Configuration) est réservée aux administrateurs. "
        "Elle permet de gérer les comptes d'accès à la console (voir capture 2.8)."
    )
    _heading(doc, "4.1 Création d'un utilisateur", 2)
    _table(doc, ["Champ", "Description"], [
        ["Identifiant", "Nom de connexion unique (lettres, chiffres, tirets)"],
        ["Prénom / Nom", "Affichés dans la console et sur les ateliers provisionnés"],
        ["Adresse e-mail", "Utilisée pour l'avatar Gravatar"],
    ])
    _note(doc, "Le mot de passe initial est « welcome ». L'utilisateur devra le changer à la première connexion.")

    _heading(doc, "4.2 Modification et suppression", 2)
    _bullet(doc, "Modifier : met à jour le prénom, nom, e-mail, rôle et mot de passe")
    _bullet(doc, "Réinit. MDP : remet le mot de passe à « welcome » avec changement obligatoire")
    _bullet(doc, "Désactiver / Activer : bloque ou rétablit l'accès sans supprimer le compte")
    _bullet(doc, "Supprimer : suppression définitive (impossible sur son propre compte)")
    _note(doc, "Tous les utilisateurs connectés peuvent provisionner des ateliers. "
              "Chaque atelier affiche le nom de la personne qui l'a créé.")

    _heading(doc, "5. Personnalisation du logo", 1)
    doc.add_paragraph(
        "La section Logo (menu Configuration) est réservée aux administrateurs. Elle permet "
        "de remplacer le logo Lab Console par celui de votre organisation. Le logo personnalisé "
        "s'affiche dans la barre latérale, l'écran de connexion et les documents PDF exportés "
        "(voir capture 2.9)."
    )
    _heading(doc, "5.1 Dimensions recommandées", 2)
    _table(doc, ["Critère", "Valeur"], [
        ["Format idéal", "Carré 256×256 pixels — PNG avec fond transparent de préférence"],
        ["Maximum", "512×512 pixels — redimensionnement automatique"],
        ["Minimum", "32×32 pixels"],
        ["Formats acceptés", "PNG, JPEG, WebP, GIF (max. 2 Mo)"],
        ["Affichage barre latérale", "28 px"],
        ["Affichage connexion", "56 px"],
        ["Affichage PDF exportés", "~45 px"],
    ])
    _heading(doc, "5.2 Téléversement et réinitialisation", 2)
    _numbered(doc, "Menu Configuration → Logo")
    _numbered(doc, "Consulter l'aperçu (barre latérale, connexion, vue agrandie)")
    _numbered(doc, "Choisir un fichier image et cliquer sur Téléverser le logo")
    _numbered(doc, "Pour revenir au logo d'origine : Rétablir le logo par défaut")
    _note(doc, "Utilisez une image carrée haute résolution (256×256 px) pour un rendu net "
              "sur tous les affichages, y compris les PDF.")

    _heading(doc, "6. Connexion Azure", 1)
    _heading(doc, "6.1 Prérequis Azure AD", 2)
    doc.add_paragraph(
        "Une application Azure AD dédiée est requise (le client Azure CLI est bloqué par les politiques "
        "Conditional Access). Créez une inscription d'application de type « Web » avec :"
    )
    _bullet(doc, "Permission API : Azure Service Management → user_impersonation")
    _bullet(doc, "Permission optionnelle : Microsoft Graph → Organization.Read.All (nom du tenant)")
    _bullet(doc, "URI de redirection : https://<votre-domaine>/api/azure/auth/callback")
    _bullet(doc, "Client Secret (colonne Valeur, pas l'ID du secret)")

    _heading(doc, "6.2 Configuration dans la console", 2)
    _numbered(doc, "Menu Configuration → Connexion Azure")
    _numbered(doc, "Saisir le Client ID, le Tenant ID (recommandé) et le Client Secret")
    _numbered(doc, "Cliquer sur Enregistrer la configuration")
    _numbered(doc, "Cliquer sur Se connecter avec Microsoft")
    _numbered(doc, "S'authentifier (MFA si activée) — message « Étape 1/2 réussie »")
    _numbered(doc, "Sélectionner la souscription de facturation")
    _numbered(doc, "Cliquer sur Utiliser cet environnement — badge Azure vert")

    _note(doc, "Le compte doit disposer du rôle Contributor sur la souscription cible. Voir capture 2.6.")

    _heading(doc, "7. Tableau de bord", 1)
    doc.add_paragraph("Le tableau de bord affiche une vue consolidée de tous les ateliers :")
    _bullet(doc, "Nombre d'ateliers, VMs totales, VMs en cours d'exécution")
    _bullet(doc, "vCPU et RAM agrégés")
    _bullet(doc, "Coût estimé total (CHF ou EUR selon la devise active)")
    _bullet(doc, "Tableau détaillé par atelier avec lien vers le détail (voir capture 2.2)")

    _heading(doc, "8. Création d'un atelier", 1)
    _heading(doc, "8.1 Informations générales", 2)
    _table(doc, ["Champ", "Description"], [
        ["Nom de l'atelier", "Identifiant lisible (ex. Formation-Docker-Mars)"],
        ["Région Azure", "francecentral, westeurope, northeurope, switzerlandnorth"],
        ["Durée", "Nombre de jours pour le calcul des coûts (1 à 365)"],
    ])

    _heading(doc, "8.2 Planification automatique", 2)
    doc.add_paragraph(
        "Par défaut, les VMs démarrent à 7h et s'arrêtent à 19h (fuseau Europe/Paris). "
        "La planification peut être désactivée pour un pilotage manuel."
    )

    _heading(doc, "8.3 Configuration des VMs", 2)
    doc.add_paragraph("Pour chaque ligne de configuration :")
    _table(doc, ["Champ", "Description"], [
        ["Préfixe de nom", "Base du nom des VMs (ex. win11 → win11-01, win11-02…)"],
        ["Système d'exploitation", "Windows 11, Windows Server 2025 ou Ubuntu"],
        ["Quantité", "Nombre de VMs à créer (1 à 100)"],
        ["Taille VM", "Standard_D4s_v3 par défaut (virtualisation imbriquée)"],
        ["Utilisateur / Mot de passe", "Optionnels — générés automatiquement si vides"],
    ])

    _heading(doc, "8.4 Estimation et création", 2)
    _numbered(doc, "L'estimation de consommation s'affiche automatiquement")
    _numbered(doc, "Optionnel : Générer l'offre PDF avant création")
    _numbered(doc, "Cliquer sur Créer l'atelier")
    _numbered(doc, "Les identifiants sont générés immédiatement, avant le déploiement Azure")
    _numbered(doc, "Le statut passe à « création en cours » avec suivi VM par VM (voir capture 2.7)")
    _note(doc, "L'atelier est associé à votre compte utilisateur (affiché dans la liste et le détail).")

    _heading(doc, "9. Gestion d'un atelier", 1)
    doc.add_paragraph("Depuis Ateliers, cliquez sur une carte pour ouvrir le détail (voir capture 2.3).")
    _heading(doc, "9.1 Statuts", 2)
    _table(doc, ["Statut", "Signification"], [
        ["création en cours", "Provisionnement Azure en cours"],
        ["prêt", "Toutes les VMs sont opérationnelles"],
        ["suppression en cours", "Groupe de ressources en cours de suppression"],
        ["erreur", "Échec du provisionnement — supprimer et recréer"],
    ])

    _heading(doc, "9.2 Actions disponibles", 2)
    _bullet(doc, "Rafraîchir : met à jour le statut (auto toutes les 8 s pendant création/suppression)")
    _bullet(doc, "Exporter PDF : identifiants de connexion de toutes les VMs")
    _bullet(doc, "Supprimer l'atelier : lance la suppression du groupe de ressources Azure")
    _bullet(doc, "Copier le mot de passe : sur chaque carte VM")

    _heading(doc, "9.3 Suivi du provisionnement", 2)
    doc.add_paragraph(
        "Pendant la création, chaque VM affiche un statut : En attente → Création Azure… → running. "
        "Le compteur indique X / Y VM(s) prête(s). Les identifiants et mots de passe sont visibles "
        "dès le début, avant l'attribution des adresses IP."
    )

    _heading(doc, "10. Estimation des coûts et offre PDF", 1)
    doc.add_paragraph("Menu Estimation coûts — permet d'anticiper les coûts sans créer d'atelier.")
    _numbered(doc, "Renseigner le nom de l'atelier et le client (optionnel)")
    _numbered(doc, "Choisir la région, la durée et la planification horaire")
    _numbered(doc, "Ajouter les configurations VM")
    _numbered(doc, "Calculer l'estimation")
    _numbered(doc, "Générer l'offre PDF")

    _note(doc, "L'offre PDF inclut le logo, le détail des coûts, le taux de change et une validité de 30 jours. Voir capture 2.5.")

    _heading(doc, "11. Documents PDF", 1)
    _table(doc, ["Document", "Quand", "Contenu"], [
        ["Offre commerciale", "Avant ou pendant la création", "Coûts, configuration, conditions"],
        ["Identifiants de connexion", "Dès que les VMs sont enregistrées", "Utilisateur, mot de passe, IP, commande RDP/SSH"],
    ])
    _note(doc, "Réexportez le PDF identifiants une fois toutes les IP assignées.")

    _heading(doc, "12. Gestion des machines virtuelles", 1)
    doc.add_paragraph("Sur une VM en statut prêt :")
    _bullet(doc, "Démarrer / Arrêter : contrôle manuel de l'alimentation")
    _bullet(doc, "Identifiants : fenêtre modale avec détails de connexion")
    doc.add_paragraph("Accès distant :")
    _bullet(doc, "Windows : RDP (port 3389) — mstsc /v:<IP>")
    _bullet(doc, "Ubuntu : SSH (port 22) — ssh <utilisateur>@<IP>")

    _heading(doc, "13. Planification automatique", 1)
    doc.add_paragraph(
        "Si activée à la création, Azure Automation provisionne des runbooks Start-LabVMs et Stop-LabVMs "
        "dans le groupe de ressources. Les VMs démarrent et s'arrêtent selon le créneau configuré."
    )

    _heading(doc, "14. Suppression d'un atelier", 1)
    _numbered(doc, "Cliquer sur Supprimer l'atelier et confirmer")
    _numbered(doc, "Le statut passe à « suppression en cours »")
    _numbered(doc, "Rafraîchir pour suivre — redirection automatique quand Azure a terminé")
    _note(doc, "Si le groupe de ressources a été supprimé manuellement dans le portail Azure, un rafraîchissement finalise la suppression en base.")

    _heading(doc, "15. Devise et taux de change", 1)
    doc.add_paragraph(
        "La console affiche les coûts en CHF par défaut. Le bouton CHF/EUR dans la barre supérieure "
        "bascule l'affichage. Le taux EUR/CHF est mis à jour automatiquement toutes les heures."
    )

    _heading(doc, "16. Dépannage", 1)
    _table(doc, ["Problème", "Solution"], [
        ["Session expirée", "Se reconnecter avec identifiant et mot de passe"],
        ["Mot de passe à changer", "Modifier le mot de passe à la première connexion"],
        ["Accès refusé à Utilisateurs / Logo", "Seuls les administrateurs gèrent les comptes et le logo"],
        ["Échec téléversement logo", "Vérifier le format (PNG, JPEG, WebP, GIF) et la taille (max. 2 Mo)"],
        ["Badge Azure « Non connecté »", "Compléter l'étape 2 : choisir une souscription"],
        ["Erreur Conditional Access", "Utiliser l'application Azure AD dédiée, pas Azure CLI"],
        ["Erreur AADSTS7000218", "Vérifier que le Client Secret est bien renseigné"],
        ["Provisionnement bloqué", "Rafraîchir, vérifier les quotas Azure, supprimer et recréer"],
        ["Suppression bloquée", "Rafraîchir — la console détecte si Azure a déjà supprimé le RG"],
        ["PDF sans IP", "Attendre la fin du provisionnement et réexporter"],
    ])

    _heading(doc, "17. Bonnes pratiques de sécurité", 1)
    for item in [
        "Restreindre l'accès réseau à la console (VPN, pare-feu)",
        "Créer un compte par formateur — éviter le partage des identifiants",
        "Désactiver ou supprimer les comptes inutilisés",
        "Ne pas diffuser les PDF d'identifiants en dehors des participants",
        "Changer SECRET_KEY en production",
        "Restreindre les NSG (RDP/SSH) à des plages IP connues en production",
        "Supprimer les ateliers en fin de formation pour limiter les coûts",
        "Surveiller le tableau de bord pour détecter les VMs oubliées en marche",
    ]:
        _bullet(doc, item)

    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = footer.add_run("— Fin du document —")
    r.font.color.rgb = BRAND_MUTED
    r.italic = True

    return doc


def main():
    import argparse
    import subprocess
    import sys

    parser = argparse.ArgumentParser(description="Génère le mode d'emploi Lab Console")
    parser.add_argument(
        "--no-capture",
        action="store_true",
        help="Ne pas relancer les captures d'écran Playwright",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    from manual_pdf import OUTPUT_PATH as PDF_OUTPUT_PATH, build_manual_pdf

    capture_script = ROOT / "scripts" / "capture_screenshots.py"
    if not args.no_capture and capture_script.exists():
        print("Capture des écrans de la console…")
        subprocess.run([sys.executable, str(capture_script)], check=False)

    pdf_path = build_manual_pdf(PDF_OUTPUT_PATH)
    print(f"Généré : {pdf_path} ({pdf_path.stat().st_size // 1024} Ko)")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = build_manual()
    doc.save(str(OUTPUT_PATH))
    import zipfile
    with zipfile.ZipFile(OUTPUT_PATH) as zf:
        media = [n for n in zf.namelist() if n.startswith("word/media/")]
    print(f"Généré : {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size // 1024} Ko, {len(media)} images)")


if __name__ == "__main__":
    main()
