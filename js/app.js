const OS_OPTIONS = [
  { value: "windows11", label: "Windows 11 (Ent)" },
  { value: "windowsserver2025", label: "Windows Server 2025" },
  { value: "ubuntu", label: "Ubuntu Server LTS" },
];

const OS_PREFIX_MAP = {
  windows11: "win11",
  windowsserver2025: "win2025",
  ubuntu: "ubuntu",
};

const OS_USER_BASE_MAP = {
  windows11: "labwin",
  windowsserver2025: "labws",
  ubuntu: "labux",
};

const VM_SIZES = [
  { value: "Standard_D2s_v3", label: "D2s_v3 (2 vCPU, 8 Go)" },
  { value: "Standard_D4s_v3", label: "D4s_v3 (4 vCPU, 16 Go)" },
  { value: "Standard_D8s_v3", label: "D8s_v3 (8 vCPU, 32 Go)" },
  { value: "Standard_D16s_v3", label: "D16s_v3 (16 vCPU, 64 Go)" },
];

let currentWorkshopId = null;
let vmCounter = 0;
let azureLoginSession = null;
let azureDevicePollTimer = null;
let workshopPollTimer = null;

function stopAzureDevicePoll() {
  if (azureDevicePollTimer) {
    clearInterval(azureDevicePollTimer);
    azureDevicePollTimer = null;
  }
}

function hideAzureDevicePanel() {
  stopAzureDevicePoll();
  document.getElementById("azure-device-panel")?.classList.add("hidden");
}

function showAzureDevicePanel(flow) {
  stopAzureDevicePoll();
  const panel = document.getElementById("azure-device-panel");
  panel.classList.remove("hidden");
  document.getElementById("azure-device-code").textContent = flow.user_code;
  document.getElementById("azure-device-message").textContent = flow.message || "";
  document.getElementById("azure-device-open").href = flow.verification_uri;

  azureDevicePollTimer = setInterval(async () => {
    try {
      const result = await API.azureDevicePoll(flow.session_id);
      if (result.status === "complete") {
        stopAzureDevicePoll();
        hideAzureDevicePanel();
        showAzureEnvPanel({
          session_id: result.session_id,
          tenant_id: result.tenant_id,
          tenant_name: result.tenant_name,
          username: result.username,
          subscriptions: result.subscriptions,
          auth_type: "oauth",
        });
        toast("Connexion Microsoft réussie");
      }
    } catch (e) {
      stopAzureDevicePoll();
      toast(e.message, "error");
    }
  }, 4000);
}

async function startAzureDeviceLogin() {
  hideAzureDevicePanel();
  try {
    const flow = await API.azureDeviceStart();
    showAzureDevicePanel(flow);
  } catch (e) {
    toast(e.message, "error");
  }
}

async function loadAzureSetup() {
  try {
    const setup = await API.azureAuthSetup();
    document.getElementById("azure-setup-instructions").textContent = setup.instructions;
    document.getElementById("azure-setup-redirect").textContent = setup.redirect_uri;
    document.getElementById("azure-config-client-id").value = setup.custom_app_configured ? setup.client_id : "";
    document.getElementById("azure-config-tenant-id").value = setup.tenant_id || "";
    document.getElementById("azure-config-client-secret").value = "";
    document.getElementById("azure-secret-status").textContent = setup.client_secret_configured
      ? "✓ Client Secret enregistré. Pour le remplacer, collez un nouveau secret puis enregistrez."
      : "Collez la colonne « Valeur » du secret Azure AD (pas l'ID/GUID), puis cliquez Enregistrer.";
    const stepsEl = document.getElementById("azure-setup-steps");
    stepsEl.innerHTML = (setup.steps || []).map((s) => `<li>${s}</li>`).join("");
    const warning = document.getElementById("azure-setup-warning");
    warning.classList.toggle("configured", setup.oauth_ready);
    const browserBtn = document.getElementById("azure-browser-login-btn");
    if (browserBtn) browserBtn.disabled = !setup.oauth_ready;
  } catch (e) {
    document.getElementById("azure-setup-instructions").textContent = e.message;
  }
}

async function saveAzureConfig() {
  const clientId = document.getElementById("azure-config-client-id").value.trim();
  const tenantId = document.getElementById("azure-config-tenant-id").value.trim();
  const secretEl = document.getElementById("azure-config-client-secret");
  const clientSecret = (secretEl?.value || "").trim();

  if (!clientId) return toast("Saisissez le Client ID de votre application Azure AD", "error");

  let setup = {};
  try {
    setup = await API.azureAuthSetup();
  } catch {
    /* ignore */
  }

  if (!clientSecret && !setup.client_secret_configured) {
    secretEl?.focus();
    return toast(
      "Collez la Valeur du secret (colonne « Valeur » dans Azure AD, pas l'ID), puis enregistrez.",
      "error"
    );
  }

  try {
    await API.azureSaveConfig({
      client_id: clientId,
      tenant_id: tenantId,
      client_secret: clientSecret || undefined,
    });
    toast("Configuration Azure enregistrée");
    loadAzureSetup();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function startAzureBrowserLogin() {
  try {
    const setup = await API.azureAuthSetup();
    const redirectUri = setup.redirect_uri;
    if (!redirectUri) return toast("URI de redirection non configurée", "error");
    const flow = await API.azureBrowserStart(redirectUri);
    window.location.href = flow.auth_url;
  } catch (e) {
    toast(e.message, "error");
  }
}

async function handleAzureCallbackFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  const sessionId = params.get("session_id");
  const authError = params.get("auth_error");
  if (authError) {
    toast(decodeURIComponent(authError), "error");
    window.history.replaceState({}, "", window.location.pathname);
    showView("azure");
    return;
  }
  if (view === "azure") showView("azure");
  if (!sessionId) return;
  try {
    const result = await API.azureAuthSession(sessionId);
    if (result.status === "complete") {
      showAzureEnvPanel({
        session_id: result.session_id,
        tenant_id: result.tenant_id,
        tenant_name: result.tenant_name,
        username: result.username,
        subscriptions: result.subscriptions,
        auth_type: "oauth",
      });
      showView("azure");
      toast("Étape 1/2 réussie — sélectionnez votre souscription ci-dessous");
    }
  } catch (e) {
    toast(e.message, "error");
  }
  window.history.replaceState({}, "", window.location.pathname);
}

const PAGE_TITLES = {
  dashboard: { title: "Tableau de bord", subtitle: "Vue consolidée de vos ateliers Azure" },
  workshops: { title: "Ateliers", subtitle: "Gérez vos environnements de formation" },
  create: { title: "Nouvel atelier", subtitle: "Créez un groupe de ressources avec des VMs de lab" },
  estimate: { title: "Estimation des coûts", subtitle: "Anticipez le coût mensuel de provisionnement" },
  azure: { title: "Connexion Azure", subtitle: "Authentification et sélection de l'environnement" },
  users: { title: "Utilisateurs", subtitle: "Gérez les comptes d'accès à la console" },
  branding: { title: "Logo", subtitle: "Personnalisez l'identité visuelle de la console" },
  "workshop-detail": { title: "Détail atelier", subtitle: "VMs, planification et identifiants" },
};

const ICONS = {
  cloud: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>',
  server: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><circle cx="6" cy="6" r="1"/><circle cx="6" cy="18" r="1"/></svg>',
  cpu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></svg>',
  cost: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
};

function openMobileNav() {
  document.querySelector(".sidebar")?.classList.add("is-open");
  const overlay = document.getElementById("sidebar-overlay");
  overlay?.classList.add("is-visible");
  overlay?.setAttribute("aria-hidden", "false");
  document.body.classList.add("mobile-nav-open");
  document.getElementById("mobile-nav-toggle")?.setAttribute("aria-expanded", "true");
}

function closeMobileNav() {
  document.querySelector(".sidebar")?.classList.remove("is-open");
  const overlay = document.getElementById("sidebar-overlay");
  overlay?.classList.remove("is-visible");
  overlay?.setAttribute("aria-hidden", "true");
  document.body.classList.remove("mobile-nav-open");
  document.getElementById("mobile-nav-toggle")?.setAttribute("aria-expanded", "false");
}

function initMobileNav() {
  document.getElementById("mobile-nav-toggle")?.addEventListener("click", () => {
    const open = document.querySelector(".sidebar")?.classList.contains("is-open");
    if (open) closeMobileNav();
    else openMobileNav();
  });
  document.getElementById("sidebar-overlay")?.addEventListener("click", closeMobileNav);
  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) closeMobileNav();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMobileNav();
  });
  document.querySelectorAll(".sidebar-nav .nav-link").forEach((link) => {
    link.addEventListener("click", closeMobileNav);
  });
}

function updateTopbar(view, customTitle) {
  const info = PAGE_TITLES[view] || PAGE_TITLES.dashboard;
  document.getElementById("page-title").textContent = customTitle || info.title;
  document.getElementById("page-subtitle").textContent = info.subtitle;
}

function updateClock() {
  const el = document.getElementById("topbar-clock");
  if (el) el.textContent = new Date().toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
}

function toast(msg, type = "success") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  setTimeout(() => el.classList.add("hidden"), 4000);
}

function showView(name, customTitle) {
  if (name !== "workshop-detail") stopWorkshopPoll();
  closeMobileNav();
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
  const view = document.getElementById(`view-${name}`);
  if (view) view.classList.add("active");
  const navName = name === "workshop-detail" ? "workshops" : name;
  const nav = document.querySelector(`[data-view="${navName}"]`);
  if (nav) nav.classList.add("active");
  updateTopbar(name, customTitle);
  if (name === "azure") loadAzureSetup();
}

function statusClass(status) {
  if (status === "ready") return "status-ready";
  if (status === "creating") return "status-creating";
  if (status === "deleting") return "status-deleting";
  return "status-error";
}

function statusLabel(status) {
  if (status === "ready") return "prêt";
  if (status === "creating") return "création en cours";
  if (status === "deleting") return "suppression en cours";
  if (status.startsWith("error")) return "erreur";
  return status;
}

function isErrorStatus(status) {
  return Boolean(status && status.startsWith("error"));
}

function errorMessage(status) {
  return isErrorStatus(status) ? status.replace(/^error:\s*/i, "") : "";
}

function workshopCreatorLine(workshop) {
  if (!workshop.created_by_display_name) return "";
  const email = workshop.created_by_email ? ` · ${workshop.created_by_email}` : "";
  return `<div class="workshop-creator">Provisionné par <strong>${workshop.created_by_display_name}</strong>${email}</div>`;
}

function stopWorkshopPoll() {
  if (workshopPollTimer) {
    clearInterval(workshopPollTimer);
    workshopPollTimer = null;
  }
}

function startWorkshopPoll(id) {
  stopWorkshopPoll();
  workshopPollTimer = setInterval(() => refreshWorkshopDetail(id, { silent: true }), 8000);
}

async function refreshWorkshopDetail(id = currentWorkshopId, options = {}) {
  if (!id) return;
  const btn = document.getElementById("workshop-refresh-btn");
  if (btn && !options.silent) {
    btn.disabled = true;
    btn.textContent = "Actualisation…";
  }
  try {
    await openWorkshop(id, { preservePoll: true });
    if (!currentWorkshopId) return;
    if (!options.silent) toast("Statut mis à jour");
  } catch (e) {
    if (!options.silent) toast(e.message, "error");
  } finally {
    if (btn && !options.silent) {
      btn.disabled = false;
      btn.innerHTML = REFRESH_BTN_HTML;
    }
  }
}

const REFRESH_BTN_HTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg> Rafraîchir`;

function powerClass(state) {
  if (state === "running") return "power-running";
  return "power-stopped";
}

function vmStatusLabel(vm) {
  if (vm.status === "pending") return "En attente";
  if (vm.status === "provisioning") {
    if (vm.provisioning_state === "Creating") return "Création Azure…";
    if (vm.provisioning_state === "Updating") return "Mise à jour…";
    return "Provisionnement…";
  }
  if (vm.provisioning_state === "Failed" || vm.status.startsWith("error")) return "Échec";
  return vm.power_state || "—";
}

function vmStatusClass(vm) {
  if (vm.status === "ready" && vm.provisioning_state !== "Failed") return powerClass(vm.power_state);
  if (vm.status === "pending") return "status-pending";
  if (vm.status === "provisioning" || vm.provisioning_state === "Creating" || vm.provisioning_state === "Updating") {
    return "status-creating";
  }
  return "status-error";
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function copyVmPassword(password) {
  navigator.clipboard.writeText(password)
    .then(() => toast("Mot de passe copié"))
    .catch(() => toast("Impossible de copier", "error"));
}

function renderVmCard(ws, vm) {
  const isReady = vm.status === "ready" && vm.id;
  return `
    <div class="vm-detail-card ${!isReady ? "vm-in-progress" : ""}">
      <div class="vm-header">
        <strong>${vm.name}</strong>
        <span class="status-badge ${vmStatusClass(vm)}">${vmStatusLabel(vm)}</span>
      </div>
      <dl class="vm-info-grid">
        <div><dt>OS</dt><dd>${vm.os_type}</dd></div>
        <div><dt>Taille</dt><dd>${vm.vm_size || "—"}</dd></div>
        <div><dt>IP publique</dt><dd>${vm.public_ip || "—"}</dd></div>
        <div><dt>IP privée</dt><dd>${vm.private_ip || "—"}</dd></div>
        <div><dt>Accès distant</dt><dd>${vm.remote_protocol ? `${vm.remote_protocol}:${vm.remote_port}` : "—"}</dd></div>
        <div><dt>Utilisateur</dt><dd>${vm.admin_username && vm.admin_username !== "—" ? vm.admin_username : "—"}</dd></div>
        <div class="vm-password-row"><dt>Mot de passe</dt><dd class="vm-password">${vm.admin_password ? escapeHtml(vm.admin_password) : "—"}</dd></div>
      </dl>
      ${vm.id ? `
        <div class="vm-actions">
          ${isReady ? `
            <button class="btn btn-secondary btn-sm" onclick="vmAction('start', ${ws.id}, '${vm.name}')">Démarrer</button>
            <button class="btn btn-secondary btn-sm" onclick="vmAction('stop', ${ws.id}, '${vm.name}')">Arrêter</button>
          ` : ""}
          ${vm.admin_password ? `<button class="btn btn-secondary btn-sm" onclick="copyVmPassword(${JSON.stringify(vm.admin_password)})">Copier le mot de passe</button>` : ""}
        </div>
      ` : ""}
    </div>
  `;
}

function createVMRow(containerId, prefix = "vm") {
  const id = ++vmCounter;
  const defaultOs = "windows11";
  const row = document.createElement("div");
  row.className = "vm-config-card";
  row.dataset.vmId = id;
  row.innerHTML = `
    <div class="vm-config-header">
      <span class="vm-config-badge">Configuration</span>
      <button type="button" class="btn btn-danger btn-sm remove-vm" title="Supprimer">✕</button>
    </div>
    <div class="vm-config-grid">
      <div class="field">
        <label>Système d'exploitation</label>
        <select name="${prefix}-os-${id}" class="vm-os-select">
          ${OS_OPTIONS.map((o) => `<option value="${o.value}" ${o.value === defaultOs ? "selected" : ""}>${o.label}</option>`).join("")}
        </select>
      </div>
      <div class="field field-quantity">
        <label>Nombre de VMs</label>
        <input type="number" name="${prefix}-qty-${id}" class="qty-input" value="1" min="1" max="100" required>
      </div>
      <div class="field">
        <label>Taille VM</label>
        <select name="${prefix}-size-${id}">
          ${VM_SIZES.map((s) => `<option value="${s.value}" ${s.value === "Standard_D4s_v3" ? "selected" : ""}>${s.label}</option>`).join("")}
        </select>
      </div>
    </div>
    <div class="vm-config-grid secondary">
      <div class="field">
        <label>Préfixe de nom <span class="field-hint">(auto selon OS)</span></label>
        <input type="text" name="${prefix}-name-${id}" class="vm-prefix-input" value="${OS_PREFIX_MAP[defaultOs]}" required>
      </div>
      <div class="field">
        <label>Préfixe utilisateur <span class="field-hint">(identifiants uniques)</span></label>
        <input type="text" name="${prefix}-user-${id}" class="vm-user-input" value="${OS_USER_BASE_MAP[defaultOs]}" placeholder="labwin">
      </div>
    </div>
    <p class="vm-config-hint" data-hint-for="${id}">
      1 VM : nom <code>${OS_PREFIX_MAP[defaultOs]}</code>, utilisateur <code>${OS_USER_BASE_MAP[defaultOs]}</code> + mot de passe unique
    </p>
  `;

  const container = document.getElementById(containerId);
  container.appendChild(row);

  const osSelect = row.querySelector(".vm-os-select");
  const prefixInput = row.querySelector(".vm-prefix-input");
  const userInput = row.querySelector(".vm-user-input");
  const qtyInput = row.querySelector(".qty-input");
  const hintEl = row.querySelector(".vm-config-hint");

  function syncFromOs() {
    const os = osSelect.value;
    if (!prefixInput.dataset.manual) {
      prefixInput.value = OS_PREFIX_MAP[os] || "vm";
    }
    if (!userInput.dataset.manual) {
      userInput.value = OS_USER_BASE_MAP[os] || "lab";
    }
    updateHint();
  }

  function updateHint() {
    const qty = parseInt(qtyInput.value, 10) || 1;
    const pfx = prefixInput.value || "vm";
    const usr = userInput.value || "lab";
    if (qty > 1) {
      hintEl.innerHTML = `
        <strong>${qty} VMs</strong> seront créées :
        <code>${pfx}-01</code> … <code>${pfx}-${String(qty).padStart(2, "0")}</code>
        · utilisateurs <code>${usr}01</code> … <code>${usr}${String(qty).padStart(2, "0")}</code>
        · mot de passe unique par VM
      `;
    } else {
      hintEl.innerHTML = `
        1 VM : nom <code>${pfx}</code>, utilisateur <code>${usr}</code> + mot de passe unique
      `;
    }
  }

  osSelect.addEventListener("change", () => {
    prefixInput.dataset.manual = "";
    userInput.dataset.manual = "";
    syncFromOs();
    triggerUpdate(containerId);
  });

  prefixInput.addEventListener("input", () => {
    prefixInput.dataset.manual = "1";
    updateHint();
    triggerUpdate(containerId);
  });

  userInput.addEventListener("input", () => {
    userInput.dataset.manual = "1";
    updateHint();
  });

  qtyInput.addEventListener("input", updateHint);
  qtyInput.addEventListener("change", () => triggerUpdate(containerId));

  row.querySelectorAll("select:not(.vm-os-select)").forEach((el) => {
    el.addEventListener("change", () => triggerUpdate(containerId));
  });

  row.querySelector(".remove-vm").addEventListener("click", () => {
    row.remove();
    triggerUpdate(containerId);
  });

  updateHint();
  if (containerId === "vm-definitions") triggerUpdate(containerId);
}

function triggerUpdate(containerId) {
  if (containerId === "vm-definitions") {
    updateVmTotalSummary();
    debouncedCostEstimate();
  }
}

function collectVMs(containerId, prefix = "vm") {
  const rows = document.querySelectorAll(`#${containerId} .vm-config-card, #${containerId} .vm-row`);
  return Array.from(rows).map((row) => {
    const id = row.dataset.vmId;
    const name_prefix = row.querySelector(`[name="${prefix}-name-${id}"]`).value.trim();
    const os_type = row.querySelector(`[name="${prefix}-os-${id}"]`).value;
    const vm_size = row.querySelector(`[name="${prefix}-size-${id}"]`).value;
    const quantity = parseInt(row.querySelector(`[name="${prefix}-qty-${id}"]`).value, 10) || 1;
    const user = row.querySelector(`[name="${prefix}-user-${id}"]`).value.trim();
    const vm = { name_prefix, os_type, vm_size, quantity };
    if (user) vm.admin_username = user;
    return vm;
  });
}

function getTotalVmCount(containerId, prefix = "vm") {
  return collectVMs(containerId, prefix).reduce((sum, v) => sum + v.quantity, 0);
}

function updateVmTotalSummary() {
  const el = document.getElementById("vm-total-summary");
  if (!el) return;
  const configs = collectVMs("vm-definitions");
  const total = configs.reduce((s, c) => s + c.quantity, 0);
  if (total === 0) {
    el.textContent = "";
    return;
  }
  const lines = configs.map((c) => `${c.quantity}× ${c.name_prefix}`).join(", ");
  el.textContent = `Total : ${total} VM(s) — ${lines}`;
}

let costEstimateTimer = null;
let lastCostEstimate = null;
let lastEstimateParams = null;
let lastEstimateResult = null;

function getQuotePdfParams(extra = {}) {
  const currency = Currency.display === "EUR" ? "EUR" : "CHF";
  const { cost_snapshot, ...rest } = extra;
  const payload = { ...rest, currency };
  if (cost_snapshot) payload.cost_snapshot = cost_snapshot;
  return payload;
}

async function downloadQuotePdf(params) {
  try {
    await API.downloadQuotePdf(getQuotePdfParams(params));
    toast("Offre PDF téléchargée");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function downloadCreateQuotePdf() {
  const params = getCreateFormParams();
  if (params.vms.length === 0) return toast("Ajoutez au moins une configuration VM", "error");
  if (!lastCostEstimate) return toast("Estimation en cours, patientez…", "error");
  await downloadQuotePdf({
    ...params,
    workshop_name: document.getElementById("ws-name").value.trim() || "Atelier Azure",
    client_name: "",
    cost_snapshot: lastCostEstimate,
  });
}

async function downloadEstimateQuotePdf() {
  if (!lastEstimateParams || !lastEstimateResult) return toast("Calculez d'abord l'estimation", "error");
  await downloadQuotePdf({
    ...lastEstimateParams,
    cost_snapshot: lastEstimateResult,
  });
}

function getCreateFormParams() {
  return {
    location: document.getElementById("ws-location").value,
    vms: collectVMs("vm-definitions"),
    schedule_start_hour: +document.getElementById("ws-start").value,
    schedule_stop_hour: +document.getElementById("ws-stop").value,
    duration_days: +document.getElementById("ws-duration").value,
  };
}

async function refreshCreateCostEstimate() {
  const params = getCreateFormParams();
  const btn = document.getElementById("create-workshop-btn");
  const preview = document.getElementById("create-cost-preview");

  if (params.vms.length === 0 || params.vms.reduce((s, v) => s + v.quantity, 0) === 0) {
    preview.classList.add("hidden");
    btn.disabled = true;
    lastCostEstimate = null;
    return;
  }

  try {
    const cost = await API.estimateCost(params);
    if (cost.exchange_rate) Currency.rate = cost.exchange_rate;
    Currency._updateRateDisplay();
    lastCostEstimate = cost;
    renderCreateCostPreview(cost);
    preview.classList.remove("hidden");
    btn.disabled = false;
  } catch (e) {
    preview.classList.add("hidden");
    btn.disabled = true;
    lastCostEstimate = null;
  }
}

function debouncedCostEstimate() {
  clearTimeout(costEstimateTimer);
  costEstimateTimer = setTimeout(refreshCreateCostEstimate, 400);
}

function renderCreateCostPreview(cost) {
  document.getElementById("cost-preview-summary").innerHTML = `
    <span class="total">${Currency.formatFromCostEstimate(cost)}</span>
    pour <strong>${cost.duration_days} jour(s)</strong>
    · ${cost.total_vm_count} VM(s)
    · ${cost.hours_per_day}h/jour
    · ${Currency.formatDailyFromCostEstimate(cost)} en moyenne
  `;
  document.getElementById("create-cost-details").innerHTML = `
    <div class="cost-summary-grid">
      <div class="cost-summary-item">
        <div class="label">VMs</div>
        <div class="value">${cost.total_vm_count}</div>
      </div>
      <div class="cost-summary-item">
        <div class="label">Durée</div>
        <div class="value">${cost.duration_days} j</div>
      </div>
      <div class="cost-summary-item">
        <div class="label">Heures/jour</div>
        <div class="value">${cost.hours_per_day}h</div>
      </div>
      <div class="cost-summary-item">
        <div class="label">Coût total</div>
        <div class="value">${Currency.formatFromCostEstimate(cost)}</div>
      </div>
    </div>
    <table class="cost-table">
      <thead><tr><th>Ressource</th><th>Qté (h)</th><th>Prix/h</th><th>Total</th></tr></thead>
      <tbody>
        ${cost.items.map((i) => `
          <tr>
            <td>${i.resource}</td>
            <td>${i.quantity}</td>
            <td>${Currency.formatLineItem(i, "unit_price")}</td>
            <td>${Currency.formatLineItem(i, "monthly_cost")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
    <p class="exchange-rate-footer">${Currency.rateLabel()}</p>
  `;
}

async function updateAzureStatus() {
  const badge = document.getElementById("azure-status");
  const info = document.getElementById("azure-connected-info");
  const loginForm = document.getElementById("azure-login-form");
  const envPanel = document.getElementById("azure-env-panel");

  try {
    const status = await API.azureStatus();
    if (status) {
      badge.className = "azure-badge connected";
      badge.innerHTML = `
        <span class="dot"></span>
        <div class="azure-badge-text">
          <span class="azure-label">Azure</span>
          <span class="azure-value">${status.subscription_name}</span>
        </div>`;
      loginForm.classList.add("hidden");
      envPanel.classList.add("hidden");
      info.classList.remove("hidden");
      info.innerHTML = `
        <div class="form-actions" style="border:none;padding:0;margin:0 0 1rem">
          <button type="button" class="btn btn-danger btn-sm" id="disconnect-btn">Déconnecter</button>
        </div>
        <div class="card-header"><h2>Environnement actif</h2></div>
        <dl class="vm-info-grid">
          <div><dt>Tenant</dt><dd>${status.tenant_name || status.tenant_id}</dd></div>
          <div><dt>Compte</dt><dd>${status.username}</dd></div>
          <div><dt>Souscription</dt><dd>${status.subscription_name}</dd></div>
          <div><dt>Subscription ID</dt><dd><code>${status.subscription_id}</code></dd></div>
        </dl>
      `;
      document.getElementById("disconnect-btn")?.addEventListener("click", disconnectAzure);
      return;
    }
  } catch {
    /* not connected */
  }

  if (azureLoginSession) {
    badge.className = "azure-badge pending";
    badge.innerHTML = `
      <span class="dot"></span>
      <div class="azure-badge-text">
        <span class="azure-label">Azure</span>
        <span class="azure-value">Étape 2 — choisir souscription</span>
      </div>`;
    info.classList.add("hidden");
    return;
  }

  badge.className = "azure-badge disconnected";
  badge.innerHTML = `
    <span class="dot"></span>
    <div class="azure-badge-text">
      <span class="azure-label">Azure</span>
      <span class="azure-value">Non connecté</span>
    </div>`;
  info.classList.add("hidden");
  if (!azureLoginSession) {
    loginForm.classList.remove("hidden");
    loginForm.classList.remove("is-validated");
    envPanel.classList.add("hidden");
  }
}

function showAzureEnvPanel(loginResult) {
  azureLoginSession = loginResult;
  document.getElementById("azure-login-form").classList.add("is-validated");
  document.getElementById("azure-env-panel").classList.remove("hidden");

  document.getElementById("env-tenant-name").textContent = loginResult.tenant_name;
  document.getElementById("env-tenant-id").innerHTML = `<code>${loginResult.tenant_id}</code>`;
  document.getElementById("env-username").textContent = loginResult.username;
  document.getElementById("env-sub-count").textContent = `${loginResult.subscriptions.length} disponible(s)`;

  const sel = document.getElementById("az-subscription");
  sel.innerHTML = loginResult.subscriptions.map((s) =>
    `<option value="${s.id}">${s.name} (${s.state})</option>`
  ).join("");
  if (loginResult.subscriptions.length === 1) {
    sel.value = loginResult.subscriptions[0].id;
  }

  updateAzureStatus();
  document.getElementById("azure-env-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetAzureLoginFlow() {
  azureLoginSession = null;
  hideAzureDevicePanel();
  document.getElementById("azure-login-form").classList.remove("is-validated", "hidden");
  document.getElementById("azure-env-panel").classList.add("hidden");
}

async function disconnectAzure() {
  try {
    await API.azureDisconnect();
    toast("Déconnecté");
    resetAzureLoginFlow();
    updateAzureStatus();
  } catch (e) {
    toast(e.message, "error");
  }
}

let lastConsumptionTimeline = null;

function _consumptionDayValue(day) {
  return Currency.display === "EUR" ? day.daily_cost_eur : day.daily_cost_chf;
}

function _consumptionCumulativeValue(day) {
  return Currency.display === "EUR" ? day.cumulative_cost_eur : day.cumulative_cost_chf;
}

function _formatChartDate(isoDate) {
  const [y, m, d] = isoDate.split("-");
  return `${d}.${m}`;
}

function renderConsumptionChart(timeline) {
  const el = document.getElementById("dashboard-consumption-chart");
  if (!el) return;
  lastConsumptionTimeline = timeline;

  if (!timeline?.days?.length) {
    el.innerHTML = `<div class="empty-state"><p>Aucune donnée de consommation disponible.</p></div>`;
    return;
  }

  const days = timeline.days;
  const values = days.map(_consumptionDayValue);
  const maxVal = Math.max(...values, 0.01);
  const suffix = Currency.display === "EUR" ? "€" : "CHF";
  const todayPoint = days.find((d) => d.is_today) || days[days.length - 1];
  const todayVal = _consumptionDayValue(todayPoint);
  const peakVal = Currency.display === "EUR"
    ? timeline.peak_daily_cost_eur
    : timeline.peak_daily_cost_chf;

  const chartW = 900;
  const chartH = 220;
  const padL = 48;
  const padR = 12;
  const padT = 16;
  const padB = 36;
  const innerW = chartW - padL - padR;
  const innerH = chartH - padT - padB;
  const barGap = 2;
  const barW = Math.max(4, (innerW - barGap * (days.length - 1)) / days.length);

  const bars = days.map((day, i) => {
    const val = _consumptionDayValue(day);
    const h = (val / maxVal) * innerH;
    const x = padL + i * (barW + barGap);
    const y = padT + innerH - h;
    const classes = [
      "consumption-bar",
      day.is_today ? "is-today" : "",
      day.is_future ? "is-future" : "",
      val <= 0 ? "is-empty" : "",
    ].filter(Boolean).join(" ");
    const workshops = day.workshops?.length
      ? day.workshops.map((w) => `${w.workshop_name}: ${Currency.format(w.daily_cost_chf, w.daily_cost_eur)}`).join("&#10;")
      : "Aucun atelier actif";
    const title = `${day.date} — ${val.toFixed(2)} ${suffix} (${day.active_workshop_count} atelier(s))&#10;${workshops}`;
    return `<rect class="${classes}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(h, day.active_workshop_count ? 2 : 0).toFixed(1)}" rx="2"><title>${title}</title></rect>`;
  }).join("");

  const cumValues = days.map(_consumptionCumulativeValue);
  const maxCum = Math.max(...cumValues, 0.01);
  const cumPoints = days.map((day, i) => {
    const x = padL + i * (barW + barGap) + barW / 2;
    const y = padT + innerH - (_consumptionCumulativeValue(day) / maxCum) * innerH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  const yTicks = [0, 0.5, 1].map((ratio) => {
    const val = maxVal * ratio;
    const y = padT + innerH - ratio * innerH;
    return `
      <line class="consumption-grid-line" x1="${padL}" y1="${y}" x2="${chartW - padR}" y2="${y}"></line>
      <text class="consumption-axis-label" x="${padL - 8}" y="${y + 4}" text-anchor="end">${val.toFixed(0)}</text>
    `;
  }).join("");

  const xLabels = days.filter((_, i) => i % Math.ceil(days.length / 8) === 0 || days[i].is_today).map((day) => {
    const i = days.indexOf(day);
    const x = padL + i * (barW + barGap) + barW / 2;
    return `<text class="consumption-axis-label" x="${x}" y="${chartH - 8}" text-anchor="middle">${_formatChartDate(day.date)}</text>`;
  }).join("");

  el.innerHTML = `
    <div class="consumption-chart-summary">
      <div class="consumption-stat">
        <span class="consumption-stat-label">Aujourd'hui</span>
        <strong>${todayVal.toFixed(2)} ${suffix}</strong>
        <span class="meta">${todayPoint.active_workshop_count} atelier(s) actif(s)</span>
      </div>
      <div class="consumption-stat">
        <span class="consumption-stat-label">Pic journalier</span>
        <strong>${peakVal.toFixed(2)} ${suffix}</strong>
        <span class="meta">${timeline.peak_date ? _formatChartDate(timeline.peak_date) : "—"}</span>
      </div>
      <div class="consumption-stat">
        <span class="consumption-stat-label">Cumul période</span>
        <strong>${_consumptionCumulativeValue(days[days.length - 1]).toFixed(2)} ${suffix}</strong>
        <span class="meta">${_formatChartDate(timeline.start_date)} → ${_formatChartDate(timeline.end_date)}</span>
      </div>
      <div class="consumption-legend">
        <span><i class="legend-swatch past"></i> Passé</span>
        <span><i class="legend-swatch today"></i> Aujourd'hui</span>
        <span><i class="legend-swatch future"></i> Projection</span>
        <span><i class="legend-line"></i> Cumul</span>
      </div>
    </div>
    <div class="consumption-chart-scroll">
      <svg class="consumption-chart" viewBox="0 0 ${chartW} ${chartH}" preserveAspectRatio="xMinYMid meet" aria-label="Évolution journalière de la consommation">
        ${yTicks}
        ${bars}
        <polyline class="consumption-cumulative" points="${cumPoints}"></polyline>
        ${xLabels}
      </svg>
    </div>
    <p class="consumption-chart-note meta">Estimation basée sur la planification horaire de chaque atelier (coût total ÷ durée). Les jours futurs sont une projection.</p>
  `;
}

async function loadDashboard() {
  const metricsEl = document.getElementById("dashboard-metrics");
  const tableEl = document.getElementById("dashboard-workshops");
  const chartEl = document.getElementById("dashboard-consumption-chart");
  try {
    const m = await API.subscriptionMetrics();
    if (m.exchange_rate) Currency.rate = m.exchange_rate;
    Currency._updateRateDisplay();
    metricsEl.innerHTML = `
      <div class="metric-card">
        <div class="metric-icon">${ICONS.cloud}</div>
        <div class="label">Souscription</div>
        <div class="value text-value">${m.subscription_name || "—"}</div>
        <div class="sub">${m.workshop_count} atelier(s)</div>
      </div>
      <div class="metric-card">
        <div class="metric-icon">${ICONS.server}</div>
        <div class="label">VMs totales</div>
        <div class="value">${m.total_vms}</div>
        <div class="sub">${m.running_vms} en cours d'exécution</div>
      </div>
      <div class="metric-card">
        <div class="metric-icon">${ICONS.cpu}</div>
        <div class="label">vCPU alloués</div>
        <div class="value">${m.total_vcpu}</div>
        <div class="sub">${m.total_ram_gb} Go RAM</div>
      </div>
      <div class="metric-card">
        <div class="metric-icon">${ICONS.cost}</div>
        <div class="label">Coût estimé</div>
        <div class="value">${Currency.formatFromMetrics(m)}</div>
        <div class="sub">Basé sur planification 7h–19h</div>
      </div>
    `;

    renderConsumptionChart(m.consumption_timeline);

    if (m.workshops.length === 0) {
      tableEl.innerHTML = `<div class="empty-state"><p>Aucun atelier pour le moment.</p><p><a href="#" onclick="showView('create');return false">Créer un premier atelier →</a></p></div>`;
      return;
    }

    tableEl.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Atelier</th>
            <th>Groupe de ressources</th>
            <th>VMs</th>
            <th>En cours</th>
            <th>vCPU</th>
            <th>RAM</th>
            <th>Coût/mois</th>
          </tr>
        </thead>
        <tbody>
          ${m.workshops.map((w) => `
            <tr style="cursor:pointer" onclick="openWorkshop(${w.workshop_id})">
              <td><strong>${w.workshop_name}</strong></td>
              <td><code>${w.resource_group}</code></td>
              <td>${w.vm_count}</td>
              <td class="${w.running_vms > 0 ? "power-running" : ""}">${w.running_vms}</td>
              <td>${w.total_vcpu}</td>
              <td>${w.total_ram_gb} Go</td>
              <td>${Currency.format(w.estimated_monthly_cost_chf, w.estimated_monthly_cost_eur)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    metricsEl.innerHTML = `<div class="empty-state"><p>Connectez-vous à Azure pour voir les métriques.</p><p><a href="#" onclick="showView('azure');return false">Configurer la connexion →</a></p></div>`;
    tableEl.innerHTML = "";
    if (chartEl) chartEl.innerHTML = "";
  }
}

async function loadWorkshops() {
  const el = document.getElementById("workshops-list");
  try {
    const workshops = await API.listWorkshops();
    if (workshops.length === 0) {
      el.innerHTML = `<div class="card card-elevated empty-state"><p>Aucun atelier pour le moment.</p><p><a href="#" onclick="showView('create');return false">Créer votre premier atelier →</a></p></div>`;
      return;
    }
    el.innerHTML = workshops.map((w) => `
      <div class="workshop-card" onclick="openWorkshop(${w.id})">
        <div class="workshop-card-header">
          <div>
            <h3>${w.name}</h3>
            <div class="meta">
              <code>${w.resource_group}</code><br>
              ${w.location} · ${w.vm_count} VM(s)
              ${workshopCreatorLine(w)}
            </div>
          </div>
          <span class="status-badge ${statusClass(w.status)}">${statusLabel(w.status)}</span>
        </div>
        <div class="workshop-card-footer">
          <span>${w.schedule_enabled ? `${w.schedule_start_hour}h → ${w.schedule_stop_hour}h` : "Planification manuelle"} · ${w.duration_days || 5}j</span>
          <span class="cost-tag">${Currency.formatFromWorkshop(w)}</span>
        </div>
      </div>
    `).join("");
  } catch (e) {
    el.innerHTML = `<div class="card"><p>Erreur: ${e.message}</p></div>`;
  }
}

async function openWorkshop(id, options = {}) {
  currentWorkshopId = id;
  const el = document.getElementById("workshop-detail");

  try {
    const [ws, vms] = await Promise.all([
      API.getWorkshop(id),
      API.getWorkshopVMs(id).catch(() => []),
    ]);
    showView("workshop-detail", ws.name);

    const isDeleting = ws.status === "deleting";
    const isCreating = ws.status === "creating";
    const isError = isErrorStatus(ws.status);
    const isPending = isDeleting || isCreating;
    const readyCount = vms.filter((v) => v.status === "ready").length;

    if (isPending && !options.preservePoll) startWorkshopPoll(id);
    if (!isPending) stopWorkshopPoll();

    el.innerHTML = `
      <div class="card card-elevated">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem;flex-wrap:wrap;gap:0.75rem">
          <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap">
            <span class="status-badge ${statusClass(ws.status)}">${statusLabel(ws.status)}</span>
            <span class="meta"><code>${ws.resource_group}</code> · ${ws.location}</span>
          </div>
          <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
            <button class="btn btn-secondary btn-sm" id="workshop-refresh-btn" onclick="refreshWorkshopDetail(${ws.id})">${REFRESH_BTN_HTML}</button>
            ${!isDeleting ? `<button class="btn btn-danger btn-sm" onclick="confirmDeleteWorkshop(${ws.id}, '${ws.name.replace(/'/g, "\\'")}')">Supprimer l'atelier</button>` : ""}
            ${vms.length > 0 && !isDeleting ? `<button class="btn btn-primary btn-sm" onclick="downloadCredentialsPdf(${ws.id}, '${ws.name.replace(/'/g, "\\'")}')">Exporter PDF</button>` : ""}
          </div>
        </div>
        ${isDeleting ? `
          <div class="workshop-status-banner deleting">
            <span class="spinner"></span>
            <div>
              <strong>Suppression en cours</strong>
              <p>Le groupe de ressources Azure <code>${ws.resource_group}</code> est en cours de suppression. Cliquez sur <em>Rafraîchir</em> ou attendez la mise à jour automatique.</p>
            </div>
          </div>
        ` : ""}
        ${isCreating ? `
          <div class="workshop-status-banner creating">
            <span class="spinner"></span>
            <div>
              <strong>Provisionnement en cours</strong>
              <p>Avancement : <strong>${readyCount} / ${ws.vm_count}</strong> VM(s) prête(s). Les identifiants sont déjà disponibles — vous pouvez <strong>Exporter PDF</strong> pendant le provisionnement (les IP seront complétées une fois les VMs créées).</p>
            </div>
          </div>
        ` : ""}
        ${isError ? `
          <div class="workshop-status-banner error">
            <div>
              <strong>Échec du provisionnement</strong>
              <p class="error-detail">${errorMessage(ws.status)}</p>
              <p>Supprimez cet atelier puis recréez-le. Si l'erreur persiste après redémarrage de l'API, contactez l'administrateur.</p>
            </div>
          </div>
        ` : ""}
        <dl class="vm-info-grid">
          <div><dt>Planification</dt><dd>${ws.schedule_enabled ? `${ws.schedule_start_hour}h → ${ws.schedule_stop_hour}h` : "Manuelle"}</dd></div>
          <div><dt>Fuseau</dt><dd>${ws.schedule_timezone}</dd></div>
          <div><dt>Durée</dt><dd>${ws.duration_days || 5} jour(s)</dd></div>
          <div><dt>Coût estimé</dt><dd><span class="cost-tag">${Currency.formatFromWorkshop(ws)}</span></dd></div>
          <div><dt>Créé le</dt><dd>${new Date(ws.created_at).toLocaleString("fr-FR")}</dd></div>
          ${ws.created_by_display_name ? `<div><dt>Provisionné par</dt><dd>${ws.created_by_display_name}${ws.created_by_email ? ` <span class="meta">(${ws.created_by_email})</span>` : ""}</dd></div>` : ""}
        </dl>
      </div>
      <div class="card card-elevated">
        <div class="card-header">
          <h2>Machines virtuelles</h2>
          <p class="card-desc">${isCreating ? `${readyCount} / ${ws.vm_count} prête(s)` : `${vms.length} VM(s)`} dans cet atelier</p>
        </div>
        ${vms.length === 0
          ? `<p>${isDeleting ? "Suppression des ressources Azure…" : isCreating ? "Initialisation du déploiement…" : isError ? "Aucune VM — le déploiement a échoué." : "Aucune VM"}</p>`
          : vms.map((vm) => renderVmCard(ws, vm)).join("")}
      </div>
    `;
  } catch (e) {
    if (e.message && (e.message.includes("introuvable") || e.message.includes("404"))) {
      stopWorkshopPoll();
      currentWorkshopId = null;
      toast("Atelier supprimé");
      showView("workshops");
      loadWorkshops();
      loadDashboard();
      return;
    }
    el.innerHTML = `<div class="card"><p>Erreur: ${e.message}</p><button class="btn btn-secondary btn-sm" onclick="refreshWorkshopDetail(${id})">Rafraîchir</button></div>`;
  }
}

async function downloadCredentialsPdf(wsId, wsName) {
  try {
    await API.downloadCredentialsPdf(wsId, wsName);
    toast("PDF téléchargé");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function showCredentials(wsId, vmId) {
  try {
    const creds = await API.getVMCredentials(wsId, vmId);
    const modal = document.getElementById("modal");
    const body = document.getElementById("modal-body");
    body.innerHTML = `
      <h3>Identifiants — ${creds.name}</h3>
      <div class="creds-box">
        <div class="row"><span class="label">Protocole: </span>${creds.remote_protocol} (port ${creds.remote_port})</div>
        <div class="row"><span class="label">Adresse: </span>${creds.public_ip || "En attente"}</div>
        <div class="row"><span class="label">Utilisateur: </span>${creds.admin_username}</div>
        <div class="row"><span class="label">Mot de passe: </span>${creds.admin_password}</div>
      </div>
      ${creds.remote_protocol === "RDP" ? `<p class="meta" style="margin-top:0.75rem">Connexion: <code>mstsc /v:${creds.public_ip}</code></p>` : `<p class="meta" style="margin-top:0.75rem">Connexion: <code>ssh ${creds.admin_username}@${creds.public_ip}</code></p>`}
    `;
    modal.classList.remove("hidden");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function vmAction(action, wsId, name) {
  try {
    if (action === "start") await API.startVM(wsId, name);
    else await API.stopVM(wsId, name);
    toast(`VM ${name} ${action === "start" ? "démarrée" : "arrêtée"}`);
    openWorkshop(wsId);
  } catch (e) {
    toast(e.message, "error");
  }
}

function confirmDeleteWorkshop(id, name) {
  if (confirm(`Supprimer l'atelier "${name}" et tout son groupe de ressources Azure ?`)) {
    deleteWorkshopAction(id);
  }
}

async function deleteWorkshopAction(id) {
  try {
    await API.deleteWorkshop(id);
    toast("Suppression lancée — suivi en cours");
    await openWorkshop(id);
    loadWorkshops();
    loadDashboard();
  } catch (e) {
    toast(e.message, "error");
  }
}

function renderCostResult(data, targetId) {
  const el = document.getElementById(targetId);
  el.classList.remove("hidden");
  el.innerHTML = `
    <div class="card-header"><h2>Résultat de l'estimation</h2></div>
    <p class="cost-preview">
      <span class="total">${Currency.formatFromCostEstimate(data)}</span>
      pour <strong>${data.duration_days} jour(s)</strong>
      · ${data.total_vm_count} VM(s)
      · ${data.hours_per_day}h/jour
      · ${Currency.formatDailyFromCostEstimate(data)} en moyenne
    </p>
    <table class="cost-table">
      <thead><tr><th>Ressource</th><th>Qté (h)</th><th>Prix/h</th><th>Total</th></tr></thead>
      <tbody>
        ${data.items.map((i) => `
          <tr>
            <td>${i.resource}</td>
            <td>${i.quantity}</td>
            <td>${Currency.formatLineItem(i, "unit_price")}</td>
            <td>${Currency.formatLineItem(i, "monthly_cost")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
    <p class="exchange-rate-footer">${Currency.rateLabel()}</p>
    <div class="form-actions" style="margin-top:1rem;padding-top:0">
      <button type="button" class="btn btn-primary btn-sm" id="estimate-quote-pdf-btn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>
        Générer l'offre PDF
      </button>
    </div>
  `;
  document.getElementById("estimate-quote-pdf-btn")?.addEventListener("click", downloadEstimateQuotePdf);
}

// Event listeners
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    const view = btn.dataset.view;
    showView(view);
    if (view === "dashboard") loadDashboard();
    if (view === "workshops") loadWorkshops();
    if (view === "users") loadUsers();
    if (view === "branding") loadBranding();
    if (view === "azure") updateAzureStatus();
  });
});

document.getElementById("back-to-workshops").addEventListener("click", () => {
  showView("workshops");
  loadWorkshops();
});

document.getElementById("add-vm-btn").addEventListener("click", () => createVMRow("vm-definitions"));
document.getElementById("add-est-vm-btn").addEventListener("click", () => createVMRow("est-vm-definitions", "est"));
document.getElementById("create-quote-pdf-btn")?.addEventListener("click", downloadCreateQuotePdf);

["ws-location", "ws-duration", "ws-start", "ws-stop"].forEach((id) => {
  document.getElementById(id)?.addEventListener("change", debouncedCostEstimate);
  document.getElementById(id)?.addEventListener("input", debouncedCostEstimate);
});

document.getElementById("create-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const vms = collectVMs("vm-definitions");
  if (vms.length === 0) return toast("Ajoutez au moins une configuration VM", "error");
  if (!lastCostEstimate) return toast("Estimation en cours, patientez…", "error");
  try {
    const ws = await API.createWorkshop({
      name: document.getElementById("ws-name").value,
      location: document.getElementById("ws-location").value,
      vms,
      duration_days: +document.getElementById("ws-duration").value,
      schedule_start_hour: +document.getElementById("ws-start").value,
      schedule_stop_hour: +document.getElementById("ws-stop").value,
      schedule_timezone: document.getElementById("ws-tz").value,
      schedule_enabled: document.getElementById("ws-schedule-enabled").checked,
    });
    toast(`Atelier "${ws.name}" en cours de création (${ws.vm_count} VMs)`);
    showView("workshops");
    loadWorkshops();
  } catch (e) {
    toast(e.message, "error");
  }
});

document.getElementById("estimate-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const vms = collectVMs("est-vm-definitions", "est");
  if (vms.length === 0) return toast("Ajoutez au moins une configuration VM", "error");
  try {
    lastEstimateParams = {
      location: document.getElementById("est-location").value,
      vms,
      schedule_start_hour: +document.getElementById("est-start").value,
      schedule_stop_hour: +document.getElementById("est-stop").value,
      duration_days: +document.getElementById("est-days").value,
      workshop_name: document.getElementById("est-workshop-name").value.trim() || "Atelier Azure",
      client_name: document.getElementById("est-client-name").value.trim(),
    };
    const cost = await API.estimateCost(lastEstimateParams);
    lastEstimateResult = cost;
    if (cost.exchange_rate) Currency.rate = cost.exchange_rate;
    Currency._updateRateDisplay();
    renderCostResult(cost, "estimate-result");
  } catch (e) {
    toast(e.message, "error");
  }
});

document.getElementById("azure-browser-login-btn").addEventListener("click", startAzureBrowserLogin);
document.getElementById("azure-config-save").addEventListener("click", saveAzureConfig);
document.getElementById("azure-device-cancel")?.addEventListener("click", hideAzureDevicePanel);

document.getElementById("azure-password-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("az-username").value.trim();
  const password = document.getElementById("az-password").value;
  if (!username || !password) return toast("Remplissez tous les champs", "error");

  const btn = document.getElementById("azure-login-btn");
  btn.disabled = true;
  btn.textContent = "Validation en cours…";

  try {
    const result = await API.azureLogin({ username, password });
    showAzureEnvPanel({ ...result, auth_type: "password" });
    toast("Connexion Azure validée");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Valider la connexion";
  }
});

document.getElementById("azure-confirm-btn").addEventListener("click", async () => {
  if (!azureLoginSession) return toast("Validez d'abord la connexion", "error");
  const sub = document.getElementById("az-subscription").value;
  if (!sub) return toast("Sélectionnez une souscription", "error");

  try {
    const payload = {
      subscription_id: sub,
    };
    if (azureLoginSession.session_id) {
      payload.session_id = azureLoginSession.session_id;
    } else {
      payload.tenant_id = azureLoginSession.tenant_id;
      payload.tenant_name = azureLoginSession.tenant_name;
      payload.username = azureLoginSession.username;
      payload.password = document.getElementById("az-password").value;
    }
    await API.azureConnect(payload);
    azureLoginSession = null;
    toast("Environnement Azure configuré");
    await updateAzureStatus();
    loadDashboard();
  } catch (e) {
    toast(e.message, "error");
  }
});

document.getElementById("azure-back-btn").addEventListener("click", () => {
  resetAzureLoginFlow();
});

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
}

document.getElementById("modal-close").addEventListener("click", closeModal);
document.getElementById("modal-backdrop").addEventListener("click", closeModal);

let usersCache = [];

async function loadUsers() {
  const el = document.getElementById("users-list");
  if (!el) return;
  try {
    const users = await API.listUsers();
    usersCache = users;
    if (users.length === 0) {
      el.innerHTML = `<div class="empty-state"><p>Aucun utilisateur.</p></div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead>
          <tr>
            <th></th>
            <th>Identifiant</th>
            <th>Nom</th>
            <th>E-mail</th>
            <th>Rôle</th>
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${users.map((u) => `
            <tr>
              <td><img src="${u.gravatar_url}" alt="" class="user-table-avatar" width="32" height="32"></td>
              <td><code>${u.username}</code></td>
              <td>${u.first_name} ${u.last_name}</td>
              <td>${u.email}</td>
              <td>${u.is_admin ? "Administrateur" : "Utilisateur"}</td>
              <td>${u.is_active ? (u.must_change_password ? "Mot de passe à changer" : "Actif") : "Désactivé"}</td>
              <td class="user-actions">
                <button class="btn btn-ghost btn-sm" onclick="openEditUser(${u.id})">Modifier</button>
                <button class="btn btn-ghost btn-sm" onclick="resetUserPassword(${u.id}, '${u.username.replace(/'/g, "\\'")}')">Réinit. MDP</button>
                ${u.id !== Auth.user?.id ? `
                  <button class="btn btn-ghost btn-sm" onclick="toggleUserActive(${u.id}, ${!u.is_active})">${u.is_active ? "Désactiver" : "Activer"}</button>
                  <button class="btn btn-danger btn-sm" onclick="confirmDeleteUser(${u.id}, '${u.username.replace(/'/g, "\\'")}')">Supprimer</button>
                ` : ""}
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><p>Erreur : ${e.message}</p></div>`;
  }
}

function openEditUser(userId) {
  const user = usersCache.find((u) => u.id === userId);
  if (!user) return toast("Utilisateur introuvable", "error");

  const isSelf = user.id === Auth.user?.id;
  const modal = document.getElementById("modal");
  const body = document.getElementById("modal-body");

  body.innerHTML = `
    <h3>Modifier l'utilisateur</h3>
    <form id="user-edit-form" class="user-edit-form">
      <div class="user-edit-header">
        <img src="${user.gravatar_url}" alt="" class="user-table-avatar" width="48" height="48">
        <div>
          <strong>${user.display_name}</strong>
          <div class="meta"><code>${user.username}</code></div>
        </div>
      </div>
      <div class="form-grid user-edit-grid">
        <div class="field">
          <label for="edit-firstname">Prénom</label>
          <input type="text" id="edit-firstname" required value="${user.first_name.replace(/"/g, "&quot;")}">
        </div>
        <div class="field">
          <label for="edit-lastname">Nom</label>
          <input type="text" id="edit-lastname" required value="${user.last_name.replace(/"/g, "&quot;")}">
        </div>
        <div class="field field-full">
          <label for="edit-email">Adresse e-mail</label>
          <input type="email" id="edit-email" required value="${user.email.replace(/"/g, "&quot;")}">
        </div>
        <div class="field field-full user-edit-checks">
          <label class="checkbox-label">
            <input type="checkbox" id="edit-is-admin" ${user.is_admin ? "checked" : ""} ${isSelf ? "disabled" : ""}>
            Administrateur
          </label>
          <label class="checkbox-label">
            <input type="checkbox" id="edit-is-active" ${user.is_active ? "checked" : ""} ${isSelf ? "disabled" : ""}>
            Compte actif
          </label>
        </div>
      </div>
      <div class="user-edit-password">
        <h4>Modifier le mot de passe</h4>
        <p class="meta">Laissez vide pour conserver le mot de passe actuel.</p>
        <div class="form-grid user-edit-grid">
          <div class="field">
            <label for="edit-password">Nouveau mot de passe</label>
            <input type="password" id="edit-password" autocomplete="new-password" minlength="6">
          </div>
          <div class="field">
            <label for="edit-password-confirm">Confirmer</label>
            <input type="password" id="edit-password-confirm" autocomplete="new-password" minlength="6">
          </div>
          <div class="field field-full">
            <label class="checkbox-label">
              <input type="checkbox" id="edit-force-password-change">
              Forcer le changement à la prochaine connexion
            </label>
          </div>
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-secondary" onclick="closeModal()">Annuler</button>
        <button type="submit" class="btn btn-primary">Enregistrer</button>
      </div>
    </form>
  `;

  document.getElementById("user-edit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const firstName = document.getElementById("edit-firstname").value.trim();
    const lastName = document.getElementById("edit-lastname").value.trim();
    const email = document.getElementById("edit-email").value.trim();
    const newPassword = document.getElementById("edit-password").value;
    const confirmPassword = document.getElementById("edit-password-confirm").value;
    const forceChange = document.getElementById("edit-force-password-change").checked;

    if (newPassword || confirmPassword) {
      if (newPassword !== confirmPassword) return toast("Les mots de passe ne correspondent pas", "error");
      if (newPassword.length < 6) return toast("Le mot de passe doit contenir au moins 6 caractères", "error");
    }

    try {
      const payload = {
        first_name: firstName,
        last_name: lastName,
        email,
      };
      if (!isSelf) {
        payload.is_admin = document.getElementById("edit-is-admin").checked;
        payload.is_active = document.getElementById("edit-is-active").checked;
      }
      const updated = await API.updateUser(userId, payload);

      if (newPassword) {
        await API.setUserPassword(userId, {
          new_password: newPassword,
          must_change_password: forceChange,
        });
      }

      if (isSelf) {
        Auth.user = await Auth.loadMe();
        Auth.updateUserMenu();
      }

      closeModal();
      toast(`Utilisateur ${updated.username} mis à jour`);
      loadUsers();
    } catch (err) {
      toast(err.message, "error");
    }
  });

  modal.classList.remove("hidden");
}

async function resetUserPassword(userId, username) {
  if (!confirm(`Réinitialiser le mot de passe de "${username}" à "welcome" ?`)) return;
  try {
    await API.resetUserPassword(userId);
    toast(`Mot de passe de ${username} réinitialisé`);
    loadUsers();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function toggleUserActive(userId, active) {
  try {
    await API.updateUser(userId, { is_active: active });
    toast(active ? "Utilisateur activé" : "Utilisateur désactivé");
    loadUsers();
  } catch (e) {
    toast(e.message, "error");
  }
}

function confirmDeleteUser(userId, username) {
  if (confirm(`Supprimer définitivement l'utilisateur "${username}" ?\n\nCette action est irréversible.`)) {
    deleteUserAction(userId, username);
  }
}

async function deleteUserAction(userId, username) {
  try {
    await API.deleteUser(userId);
    toast(`Utilisateur ${username} supprimé`);
    loadUsers();
  } catch (e) {
    toast(e.message, "error");
  }
}

document.getElementById("user-create-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await API.createUser({
      username: document.getElementById("user-username").value.trim(),
      first_name: document.getElementById("user-firstname").value.trim(),
      last_name: document.getElementById("user-lastname").value.trim(),
      email: document.getElementById("user-email").value.trim(),
    });
    toast("Utilisateur créé — mot de passe initial : welcome");
    e.target.reset();
    loadUsers();
  } catch (err) {
    toast(err.message, "error");
  }
});

document.getElementById("login-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("login-submit");
  btn.disabled = true;
  try {
    const user = await Auth.login(
      document.getElementById("login-username").value.trim(),
      document.getElementById("login-password").value,
    );
    Auth.updateUserMenu();
    if (user.must_change_password) {
      Auth.showPasswordChange(true);
      document.getElementById("pwd-current").value = "welcome";
    } else {
      Auth.showApp();
      await bootApp();
    }
    toast(`Bienvenue, ${user.display_name}`);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("password-change-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const current = document.getElementById("pwd-current").value;
  const newPwd = document.getElementById("pwd-new").value;
  const confirm = document.getElementById("pwd-confirm").value;
  if (newPwd !== confirm) return toast("Les mots de passe ne correspondent pas", "error");
  if (newPwd.length < 6) return toast("Le mot de passe doit contenir au moins 6 caractères", "error");
  try {
    await Auth.changePassword(current, newPwd);
    Auth.updateUserMenu();
    Auth.showApp();
    await bootApp();
    toast("Mot de passe mis à jour");
  } catch (err) {
    toast(err.message, "error");
  }
});

document.getElementById("user-logout-btn")?.addEventListener("click", () => {
  Auth.logout();
  toast("Déconnexion");
});

async function loadBranding() {
  const statusEl = document.getElementById("branding-status");
  try {
    const info = await Branding.refreshInfo();
    if (statusEl) {
      statusEl.textContent = info.custom
        ? "Logo personnalisé actif"
        : "Logo par défaut Lab Console";
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = `Erreur : ${e.message}`;
  }
}

document.getElementById("branding-upload-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("branding-file");
  const file = input?.files?.[0];
  if (!file) return toast("Sélectionnez un fichier image", "error");

  const btn = document.getElementById("branding-upload-btn");
  btn.disabled = true;
  try {
    const result = await API.uploadLogo(file);
    Branding.apply(result.url);
    toast(`Logo mis à jour (${result.width}×${result.height} px)`);
    document.getElementById("branding-status").textContent = "Logo personnalisé actif";
    input.value = "";
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("branding-reset-btn")?.addEventListener("click", async () => {
  if (!confirm("Rétablir le logo par défaut de Lab Console ?")) return;
  try {
    const result = await API.resetLogo();
    Branding.apply(result.url);
    toast("Logo par défaut rétabli");
    document.getElementById("branding-status").textContent = "Logo par défaut Lab Console";
    document.getElementById("branding-file").value = "";
  } catch (err) {
    toast(err.message, "error");
  }
});

async function bootApp() {
  await Currency.init();
  handleAzureCallbackFromUrl();
  await updateAzureStatus();
  updateTopbar("dashboard");
  updateClock();
  loadDashboard();
  refreshCreateCostEstimate();
}

// Init
initMobileNav();
createVMRow("vm-definitions");
createVMRow("est-vm-definitions", "est");
Branding.init().then(() => {
  Auth.init().then(async (ready) => {
    if (!ready) return;
    await bootApp();
  });
});
setInterval(updateClock, 30000);

// Auto-refresh dashboard
setInterval(() => {
  const dash = document.getElementById("view-dashboard");
  if (dash.classList.contains("active")) loadDashboard();
}, 30000);

// Expose for inline handlers
window.toggleUserActive = toggleUserActive;
window.resetUserPassword = resetUserPassword;
window.openEditUser = openEditUser;
window.confirmDeleteUser = confirmDeleteUser;
window.copyVmPassword = copyVmPassword;
window.downloadCredentialsPdf = downloadCredentialsPdf;
window.openWorkshop = openWorkshop;
window.showCredentials = showCredentials;
window.vmAction = vmAction;
window.confirmDeleteWorkshop = confirmDeleteWorkshop;
window.refreshWorkshopDetail = refreshWorkshopDetail;
window.showView = showView;
