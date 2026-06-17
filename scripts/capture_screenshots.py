#!/usr/bin/env python3
"""Capture les écrans de la console pour le mode d'emploi."""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
BASE_URL = "http://127.0.0.1/"
LOGIN_USER = "admin"
LOGIN_PASSWORD = "admin"

VIEWS = [
    ("01-tableau-de-bord", "dashboard", "Tableau de bord"),
    ("02-ateliers", "workshops", "Ateliers"),
    ("03-nouvel-atelier", "create", "Nouvel atelier"),
    ("04-estimation-couts", "estimate", "Estimation coûts"),
    ("05-connexion-azure", "azure", "Connexion Azure"),
    ("07-utilisateurs", "users", "Utilisateurs"),
]

WORKSHOP_DETAIL_HTML = """
<div class="card card-elevated">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem;flex-wrap:wrap;gap:0.75rem">
    <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap">
      <span class="status-badge status-creating">création en cours</span>
      <span class="meta"><code>rg-lab-formation-azure</code> · francecentral</span>
    </div>
    <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
      <button class="btn btn-secondary btn-sm">Rafraîchir</button>
      <button class="btn btn-danger btn-sm">Supprimer l'atelier</button>
      <button class="btn btn-primary btn-sm">Exporter PDF</button>
    </div>
  </div>
  <div class="workshop-status-banner creating">
    <span class="spinner"></span>
    <div>
      <strong>Provisionnement en cours</strong>
      <p>Avancement : <strong>2 / 5</strong> VM(s) prête(s). Les identifiants sont déjà disponibles.</p>
    </div>
  </div>
  <dl class="vm-info-grid">
    <div><dt>Planification</dt><dd>7h → 19h</dd></div>
    <div><dt>Durée</dt><dd>5 jour(s)</dd></div>
    <div><dt>Provisionné par</dt><dd>Admin Console</dd></div>
    <div><dt>Créé le</dt><dd>17/06/2026 14:30:00</dd></div>
  </dl>
</div>
<div class="card card-elevated">
  <div class="card-header"><h2>Machines virtuelles</h2><p class="card-desc">2 / 5 prête(s) dans cet atelier</p></div>
  <div class="vm-detail-card vm-in-progress">
    <div class="vm-header"><strong>win11-01</strong><span class="status-badge status-creating">Création Azure…</span></div>
    <dl class="vm-info-grid">
      <div><dt>OS</dt><dd>windows11</dd></div>
      <div><dt>Utilisateur</dt><dd>labwin01</dd></div>
      <div class="vm-password-row"><dt>Mot de passe</dt><dd class="vm-password">Kx9#mP2vLq8!</dd></div>
    </dl>
  </div>
  <div class="vm-detail-card">
    <div class="vm-header"><strong>win11-02</strong><span class="status-badge power-running">running</span></div>
    <dl class="vm-info-grid">
      <div><dt>IP publique</dt><dd>20.123.45.67</dd></div>
      <div><dt>Utilisateur</dt><dd>labwin02</dd></div>
      <div class="vm-password-row"><dt>Mot de passe</dt><dd class="vm-password">Rt4$nW7yHp3@</dd></div>
    </dl>
    <div class="vm-actions">
      <button class="btn btn-secondary btn-sm">Démarrer</button>
      <button class="btn btn-secondary btn-sm">Arrêter</button>
    </div>
  </div>
</div>
"""

USERS_TABLE_HTML = """
<table>
  <thead>
    <tr>
      <th></th><th>Identifiant</th><th>Nom</th><th>E-mail</th><th>Rôle</th><th>Statut</th><th>Actions</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><img src="https://www.gravatar.com/avatar/?d=mp&s=32" class="user-table-avatar" width="32" height="32"></td>
      <td><code>admin</code></td><td>Admin Console</td><td>admin@lab-console.local</td>
      <td>Administrateur</td><td>Actif</td>
      <td class="user-actions"><button class="btn btn-ghost btn-sm">Modifier</button></td>
    </tr>
    <tr>
      <td><img src="https://www.gravatar.com/avatar/?d=mp&s=32" class="user-table-avatar" width="32" height="32"></td>
      <td><code>formateur</code></td><td>Jean Dupont</td><td>jean.dupont@entreprise.ch</td>
      <td>Utilisateur</td><td>Mot de passe à changer</td>
      <td class="user-actions">
        <button class="btn btn-ghost btn-sm">Modifier</button>
        <button class="btn btn-ghost btn-sm">Réinit. MDP</button>
        <button class="btn btn-danger btn-sm">Supprimer</button>
      </td>
    </tr>
  </tbody>
</table>
"""


def _activate_view(page, view_id: str, title: str, subtitle: str):
    page.evaluate(
        f"""() => {{
          document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
          document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
          const view = document.getElementById('view-{view_id}');
          const nav = document.querySelector('[data-view="{view_id}"]');
          if (view) view.classList.add('active');
          if (nav) {{
            nav.classList.remove('hidden');
            nav.classList.add('active');
          }}
          document.getElementById('page-title').textContent = {title!r};
          document.getElementById('page-subtitle').textContent = {subtitle!r};
        }}"""
    )


def _login(page):
    page.fill("#login-username", LOGIN_USER)
    page.fill("#login-password", LOGIN_PASSWORD)
    page.click("#login-submit")
    page.wait_for_timeout(2500)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(1500)

        login_path = OUT / "00-connexion-console.png"
        page.locator("#login-screen").screenshot(path=str(login_path))
        print(f"Capturé : {login_path}")

        _login(page)

        titles = {
            "dashboard": ("Tableau de bord", "Vue consolidée de vos ateliers Azure"),
            "workshops": ("Ateliers", "Gérez vos environnements de formation"),
            "create": ("Nouvel atelier", "Créez un groupe de ressources et provisionnez les VMs"),
            "estimate": ("Estimation des coûts", "Anticipez le coût mensuel de provisionnement"),
            "azure": ("Connexion Azure", "Configurez la connexion à votre environnement"),
            "users": ("Utilisateurs", "Gérez les comptes d'accès à la console"),
        }

        for filename, view_id, _label in VIEWS:
            t = titles[view_id]
            _activate_view(page, view_id, t[0], t[1])
            if view_id == "users":
                page.evaluate(
                    f"""() => {{
                      document.getElementById('users-list').innerHTML = {USERS_TABLE_HTML!r};
                    }}"""
                )
            page.wait_for_timeout(1000)
            path = OUT / f"{filename}.png"
            page.screenshot(path=str(path), full_page=True)
            print(f"Capturé : {path}")

        page.evaluate(
            f"""() => {{
              document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
              document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
              document.getElementById('view-workshop-detail').classList.add('active');
              document.querySelector('[data-view="workshops"]').classList.add('active');
              document.getElementById('page-title').textContent = 'Formation Azure';
              document.getElementById('page-subtitle').textContent = 'VMs, planification et identifiants';
              document.getElementById('workshop-detail').innerHTML = {WORKSHOP_DETAIL_HTML!r};
            }}"""
        )
        page.wait_for_timeout(1000)
        detail_path = OUT / "06-detail-atelier.png"
        page.screenshot(path=str(detail_path), full_page=True)
        print(f"Capturé : {detail_path}")

        browser.close()


if __name__ == "__main__":
    main()
