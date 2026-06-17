const Currency = {
  DISPLAY_KEY: "lab-console-currency",
  default: "CHF",
  rate: null,

  async init() {
    const saved = localStorage.getItem(this.DISPLAY_KEY);
    this.display = saved || this.default;
    await this.refreshRate();
    setInterval(() => this.refreshRate(), 3600000);
    this._renderToggle();
    this._updateRateDisplay();
  },

  async refreshRate() {
    try {
      this.rate = await API.getExchangeRate();
      this._updateRateDisplay();
      this._refreshCostDisplays();
    } catch (e) {
      console.warn("Exchange rate unavailable:", e);
    }
  },

  get display() {
    return localStorage.getItem(this.DISPLAY_KEY) || this.default;
  },

  set display(val) {
    localStorage.setItem(this.DISPLAY_KEY, val);
    this._renderToggle();
    this._refreshCostDisplays();
  },

  toggle() {
    this.display = this.display === "CHF" ? "EUR" : "CHF";
  },

  format(amountChf, amountEur, opts = {}) {
    const { suffix = "", decimals = 2 } = opts;
    if (this.display === "EUR") {
      const val = amountEur ?? (this.rate ? amountChf / this.rate.eur_to_chf : amountChf);
      return `${val.toFixed(decimals)} €${suffix}`;
    }
    const val = amountChf ?? (this.rate ? amountEur * this.rate.eur_to_chf : amountEur);
    return `${val.toFixed(decimals)} CHF${suffix}`;
  },

  formatFromWorkshop(ws) {
    const suffix = ws.duration_days ? ` / ${ws.duration_days}j` : "";
    return this.format(ws.estimated_monthly_cost_chf, ws.estimated_monthly_cost_eur, { suffix });
  },

  formatFromMetrics(m) {
    return this.format(m.estimated_monthly_cost_chf, m.estimated_monthly_cost_eur);
  },

  formatFromCostEstimate(cost) {
    return this.format(cost.total_workshop_chf, cost.total_workshop_eur);
  },

  formatDailyFromCostEstimate(cost) {
    return this.format(cost.total_daily_chf, cost.total_daily_eur, { suffix: "/jour" });
  },

  formatLineItem(item, field) {
    const key = field === "monthly_cost" ? "monthly_cost" : "unit_price";
    if (this.display === "EUR") {
      return `${item[`${key}_eur`].toFixed(field === "unit_price" ? 4 : 2)} €`;
    }
    return `${item[`${key}_chf`].toFixed(field === "unit_price" ? 4 : 2)} CHF`;
  },

  rateLabel() {
    if (!this.rate) return "";
    return `1 € = ${this.rate.eur_to_chf.toFixed(4)} CHF · ${this.rate.updated_at}`;
  },

  _renderToggle() {
    const wrap = document.getElementById("currency-toggle");
    if (!wrap) return;
    wrap.innerHTML = `
      <button class="currency-btn ${this.display === "CHF" ? "active" : ""}" data-currency="CHF">CHF</button>
      <button class="currency-btn ${this.display === "EUR" ? "active" : ""}" data-currency="EUR">EUR</button>
    `;
    wrap.querySelectorAll(".currency-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.display = btn.dataset.currency;
      });
    });
  },

  _updateRateDisplay() {
    const el = document.getElementById("exchange-rate-info");
    if (el && this.rate) {
      el.textContent = this.rateLabel();
      el.title = `Source: ${this.rate.source}`;
    }
  },

  _refreshCostDisplays() {
    const dash = document.getElementById("view-dashboard");
    if (dash?.classList.contains("active")) loadDashboard();
    const ws = document.getElementById("view-workshops");
    if (ws?.classList.contains("active")) loadWorkshops();
    if (currentWorkshopId) openWorkshop(currentWorkshopId);
  },
};
