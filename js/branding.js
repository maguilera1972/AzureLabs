const Branding = {
  logoUrl: "/api/branding/logo?v=default",

  async init() {
    try {
      const info = await fetch("/api/branding/logo/info").then((r) => r.json());
      this.logoUrl = info.url;
    } catch {
      this.logoUrl = "/api/branding/logo?v=default";
    }
    this.apply();
  },

  apply(url) {
    if (url) this.logoUrl = url;
    document.querySelectorAll("[data-app-logo]").forEach((img) => {
      img.src = this.logoUrl;
    });
  },

  async refreshInfo() {
    const info = await API.brandingInfo();
    this.apply(info.url);
    return info;
  },
};

window.Branding = Branding;
