const API = {
  async request(path, options = {}) {
    const res = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...Auth.authHeaders(),
        ...options.headers,
      },
      ...options,
    });
    if (res.status === 401 && !path.includes("/api/auth/login")) {
      Auth.logout();
      throw new Error("Session expirée — reconnectez-vous");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const detail = err.detail;
      const message = typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || d).join(", ")
          : res.statusText;
      throw new Error(message || res.statusText);
    }
    if (res.status === 204) return null;
    return res.json();
  },

  health: () => API.request("/api/health"),
  login: (data) => API.request("/api/auth/login", { method: "POST", body: JSON.stringify(data) }),
  authMe: () => API.request("/api/auth/me"),
  changePassword: (data) => API.request("/api/auth/change-password", { method: "POST", body: JSON.stringify(data) }),

  listUsers: () => API.request("/api/users"),
  createUser: (data) => API.request("/api/users", { method: "POST", body: JSON.stringify(data) }),
  updateUser: (id, data) => API.request(`/api/users/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  resetUserPassword: (id) => API.request(`/api/users/${id}/reset-password`, { method: "POST", body: "{}" }),
  setUserPassword: (id, data) => API.request(`/api/users/${id}/set-password`, { method: "POST", body: JSON.stringify(data) }),
  deleteUser: (id) => API.request(`/api/users/${id}`, { method: "DELETE" }),

  brandingInfo: () => API.request("/api/branding/logo/info"),
  uploadLogo: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/branding/logo", {
      method: "POST",
      headers: Auth.authHeaders(),
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const detail = err.detail;
      const message = typeof detail === "string" ? detail : res.statusText;
      throw new Error(message || res.statusText);
    }
    return res.json();
  },
  resetLogo: () => API.request("/api/branding/logo", { method: "DELETE" }),

  azureStatus: () => API.request("/api/azure/status").catch(() => null),
  azureAuthSetup: () => API.request("/api/azure/auth/setup"),
  azureSaveConfig: (data) => API.request("/api/azure/auth/config", { method: "PUT", body: JSON.stringify(data) }),
  azureDeviceStart: () => API.request("/api/azure/auth/device/start", { method: "POST", body: "{}" }),
  azureDevicePoll: (sessionId) => API.request("/api/azure/auth/device/poll", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  }),
  azureBrowserStart: (redirectUri) => API.request("/api/azure/auth/browser/start", {
    method: "POST",
    body: JSON.stringify({ redirect_uri: redirectUri || null }),
  }),
  azureAuthSession: (sessionId) => API.request(`/api/azure/auth/session/${sessionId}`),
  azureLogin: (data) => API.request("/api/azure/login", { method: "POST", body: JSON.stringify(data) }),
  azureConnect: (data) => API.request("/api/azure/connect", { method: "POST", body: JSON.stringify(data) }),
  azureDisconnect: () => API.request("/api/azure/disconnect", { method: "DELETE" }),

  listWorkshops: () => API.request("/api/workshops"),
  getWorkshop: (id) => API.request(`/api/workshops/${id}`),
  createWorkshop: (data) => API.request("/api/workshops", { method: "POST", body: JSON.stringify(data) }),
  deleteWorkshop: (id) => API.request(`/api/workshops/${id}`, { method: "DELETE" }),
  getWorkshopVMs: (id) => API.request(`/api/workshops/${id}/vms`),
  getVMCredentials: (wsId, vmId) => API.request(`/api/workshops/${wsId}/vms/${vmId}/credentials`),
  downloadCredentialsPdf: async (wsId, wsName) => {
    const res = await fetch(`/api/workshops/${wsId}/credentials.pdf`, {
      headers: Auth.authHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `identifiants-${wsName.replace(/[^a-zA-Z0-9-]/g, "-")}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  },
  estimateCost: (data) => API.request("/api/workshops/estimate", { method: "POST", body: JSON.stringify(data) }),
  downloadQuotePdf: async (data) => {
    const res = await fetch("/api/workshops/estimate/quote.pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...Auth.authHeaders() },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const slug = (data.workshop_name || "offre").replace(/[^a-zA-Z0-9-]/g, "-");
    a.download = `offre-${slug}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  },
  subscriptionMetrics: () => API.request("/api/workshops/metrics/subscription"),
  getExchangeRate: () => API.request("/api/currency/rate"),

  startVM: (wsId, name) => API.request(`/api/vms/${wsId}/${name}/start`, { method: "POST" }),
  stopVM: (wsId, name) => API.request(`/api/vms/${wsId}/${name}/stop`, { method: "POST" }),
};
