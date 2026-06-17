const Auth = {
  TOKEN_KEY: "lab_console_token",
  user: null,

  getToken() {
    return sessionStorage.getItem(this.TOKEN_KEY);
  },

  setToken(token) {
    if (token) sessionStorage.setItem(this.TOKEN_KEY, token);
    else sessionStorage.removeItem(this.TOKEN_KEY);
  },

  authHeaders() {
    const token = this.getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  },

  async _authRequest(path, options = {}) {
    const res = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...this.authHeaders(),
        ...options.headers,
      },
      ...options,
    });
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

  async login(username, password) {
    const data = await this._authRequest("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    this.setToken(data.access_token);
    this.user = data.user;
    return data.user;
  },

  async loadMe() {
    const token = this.getToken();
    if (!token) return null;
    try {
      const user = await this._authRequest("/api/auth/me");
      this.user = user;
      return user;
    } catch {
      this.setToken(null);
      this.user = null;
      return null;
    }
  },

  async changePassword(currentPassword, newPassword) {
    const user = await this._authRequest("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    this.user = user;
    return user;
  },

  logout() {
    this.setToken(null);
    this.user = null;
    this.showLogin();
    this.updateUserMenu();
    document.querySelector(".app")?.classList.add("hidden");
    document.getElementById("login-screen")?.classList.remove("hidden");
  },

  showLogin() {
    document.getElementById("login-screen")?.classList.remove("hidden");
    document.querySelector(".app")?.classList.add("hidden");
    document.getElementById("password-change-screen")?.classList.add("hidden");
  },

  showApp() {
    document.getElementById("login-screen")?.classList.add("hidden");
    document.getElementById("password-change-screen")?.classList.add("hidden");
    document.querySelector(".app")?.classList.remove("hidden");
  },

  showPasswordChange(required = true) {
    const screen = document.getElementById("password-change-screen");
    const note = document.getElementById("password-change-note");
    if (screen) screen.classList.remove("hidden");
    document.querySelector(".app")?.classList.add("hidden");
    if (note) {
      note.textContent = required
        ? "Pour des raisons de sécurité, vous devez changer votre mot de passe avant d'accéder à la console."
        : "Choisissez un nouveau mot de passe.";
    }
  },

  updateUserMenu() {
    const menu = document.getElementById("user-menu");
    const avatar = document.getElementById("user-avatar");
    const nameEl = document.getElementById("user-display-name");
    const usersNav = document.getElementById("nav-users");
    const brandingNav = document.getElementById("nav-branding");

    if (!this.user) {
      menu?.classList.add("hidden");
      usersNav?.classList.add("hidden");
      brandingNav?.classList.add("hidden");
      return;
    }

    menu?.classList.remove("hidden");
    if (avatar) {
      avatar.src = this.user.gravatar_url;
      avatar.alt = this.user.display_name;
    }
    if (nameEl) nameEl.textContent = this.user.display_name;

    if (usersNav) {
      usersNav.classList.toggle("hidden", !this.user.is_admin);
    }
    if (brandingNav) {
      brandingNav.classList.toggle("hidden", !this.user.is_admin);
    }
  },

  async init() {
    const user = await this.loadMe();
    if (!user) {
      this.showLogin();
      return false;
    }
    this.updateUserMenu();
    if (user.must_change_password) {
      this.showPasswordChange(true);
      const currentField = document.getElementById("pwd-current");
      if (currentField && !currentField.value) currentField.value = "welcome";
      return false;
    }
    this.showApp();
    return true;
  },
};

window.Auth = Auth;
