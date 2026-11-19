/**
 * SoftEther VPN Log Panel - Main Frontend Application
 */

const App = {
  state: {
    lang: localStorage.getItem("panel_lang") || "fa",
    theme: localStorage.getItem("panel_theme") || "dark",
    currentUser: null,
    activeTab: "dashboard",
    token: localStorage.getItem("panel_token") || null,
    reportPage: 1,
    auditPage: 1,
    usernames: [],
    hubs: []
  },

  i18n: {
    fa: {
      appName: "پنل لاگ SoftEther VPN",
      appSub: "سامانه مدیریت و تحلیل نشست‌ها",
      dashboard: "داشبورد اصلی",
      reports: "گزارشات کاربران",
      sync: "همگام‌سازی لاگ",
      users: "کاربران پنل",
      audit: "گزارش فعالیت‌ها",
      logout: "خروج از حساب",
      login: "ورود به سامانه",
      welcome: "خوش آمدید",
      totalVpnUsers: "کل کاربران VPN",
      totalSessions: "کل نشست‌ها",
      activeSessions: "نشست‌های باز در لاگ",
      incompleteSessions: "نشست‌های ناقص",
      totalDuration: "مجموع زمان اتصال",
      qualityRating: "دقت تطبیق نشست‌ها",
      topUsersTitle: "کاربران با بیشترین مدت زمان اتصال",
      recentEventsTitle: "رویدادهای اخیر سرور",
      activityChartTitle: "نمودار فعالیت روزانه اتصالات",
      username: "نام کاربری",
      hub: "هاب مجازی",
      duration: "مدت اتصال",
      lastSeen: "آخرین مشاهده",
      status: "وضعیت",
      search: "جستجو و فیلتر",
      reset: "پاک‌سازی فیلترها",
      dateFrom: "از تاریخ",
      dateTo: "تا تاریخ",
      quickFilters: "فیلترهای سریع",
      today: "امروز",
      yesterday: "دیروز",
      last7Days: "۷ روز گذشته",
      last30Days: "۳۰ روز گذشته",
      thisMonth: "این ماه",
      exportExcel: "خروجی اکسل (Excel)",
      exportCsv: "خروجی CSV",
      loginTime: "زمان ورود",
      logoutTime: "زمان خروج",
      clientIp: "آی‌پی کلاینت",
      sessionId: "شناسه نشست",
      reason: "علت / توضیحات",
      completed: "تکمیل‌شده",
      active: "در حال اتصال",
      incomplete: "ناقص / قطع ناگهانی",
      syncTitle: "مدیریت و وضعیت همگام‌سازی لاگ‌ها",
      triggerSync: "شروع همگام‌سازی دستی",
      trackedFiles: "فایل‌های ردیابی‌شده لاگ",
      diagnosticsTitle: "عیب‌یابی مسیر و تنظیمات لاگ",
      role: "نقش کاربری",
      actions: "عملیات",
      addUser: "افزودن کاربر جدید",
      changePassword: "تغییر رمز عبور",
      delete: "حذف",
      activeState: "وضعیت فعال",
      save: "ذخیره اطلاعات",
      cancel: "انصراف",
      adminCreatedSuccess: "مدیر با موفقیت ایجاد شد",
      syncSuccess: "همگام‌سازی با موفقیت انجام شد"
    },
    en: {
      appName: "SoftEther VPN Log Panel",
      appSub: "Session Management & Analytics",
      dashboard: "Dashboard",
      reports: "VPN User Reports",
      sync: "Log Sync & Health",
      users: "Panel Users",
      audit: "Audit Logs",
      logout: "Logout",
      login: "Login",
      welcome: "Welcome",
      totalVpnUsers: "Total VPN Users",
      totalSessions: "Total Sessions",
      activeSessions: "Open Sessions (In Log)",
      incompleteSessions: "Incomplete Sessions",
      totalDuration: "Total Connection Time",
      qualityRating: "Parser Accuracy",
      topUsersTitle: "Top Active VPN Users",
      recentEventsTitle: "Recent Server Events",
      activityChartTitle: "Daily Connection Activity",
      username: "Username",
      hub: "Virtual Hub",
      duration: "Duration",
      lastSeen: "Last Seen",
      status: "Status",
      search: "Search & Filter",
      reset: "Reset Filters",
      dateFrom: "Date From",
      dateTo: "Date To",
      quickFilters: "Quick Filters",
      today: "Today",
      yesterday: "Yesterday",
      last7Days: "Last 7 Days",
      last30Days: "Last 30 Days",
      thisMonth: "This Month",
      exportExcel: "Export Excel",
      exportCsv: "Export CSV",
      loginTime: "Login Time",
      logoutTime: "Logout Time",
      clientIp: "Client IP",
      sessionId: "Session ID",
      reason: "Status Reason",
      completed: "Completed",
      active: "Active",
      incomplete: "Incomplete",
      syncTitle: "Log Synchronization & Tracking",
      triggerSync: "Trigger Manual Sync",
      trackedFiles: "Tracked Log Files",
      diagnosticsTitle: "Log Path Diagnostics",
      role: "Role",
      actions: "Actions",
      addUser: "Add New User",
      changePassword: "Change Password",
      delete: "Delete",
      activeState: "Active Status",
      save: "Save",
      cancel: "Cancel",
      adminCreatedSuccess: "Administrator created successfully",
      syncSuccess: "Log synchronization completed successfully"
    }
  },

  t(key) {
    const dict = this.i18n[this.state.lang] || this.i18n.fa;
    return dict[key] || key;
  },

  escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  },

  async init() {
    this.applyTheme(this.state.theme);
    this.applyLang(this.state.lang);

    // Check first-run status
    await this.checkFirstRun();

    // Check auth status
    await this.checkAuth();

    this.bindEvents();
  },

  applyTheme(theme) {
    this.state.theme = theme;
    localStorage.setItem("panel_theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
    const btn = document.getElementById("theme-toggle-btn");
    if (btn) btn.innerText = theme === "dark" ? "☀️" : "🌙";
  },

  applyLang(lang) {
    this.state.lang = lang;
    localStorage.setItem("panel_lang", lang);
    document.documentElement.setAttribute("dir", lang === "fa" ? "rtl" : "ltr");
    document.documentElement.setAttribute("lang", lang);
    const langBtn = document.getElementById("lang-toggle-btn");
    if (langBtn) langBtn.innerText = lang === "fa" ? "English" : "فارسی";
    this.updateStaticTranslations();
  },

  updateStaticTranslations() {
    document.querySelectorAll("[data-i18n]").forEach(el => {
      const key = el.getAttribute("data-i18n");
      el.innerText = this.t(key);
    });
  },

  async checkFirstRun() {
    try {
      const res = await fetch("/api/auth/setup-status");
      const data = await res.json();
      if (data.setup_needed) {
        this.showSetupModal();
      }
    } catch (e) {
      console.error("Error checking setup status:", e);
    }
  },

  async checkAuth() {
    try {
      const res = await fetch("/api/auth/me", {
        headers: this.getAuthHeaders()
      });
      if (res.ok) {
        this.state.currentUser = await res.json();
        this.renderUserBadge();
        this.hideLoginModal();
        this.loadCurrentTab();
      } else {
        this.showLoginModal();
      }
    } catch (e) {
      this.showLoginModal();
    }
  },

  getAuthHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (this.state.token) {
      headers["Authorization"] = `Bearer ${this.state.token}`;
    }
    return headers;
  },

  renderUserBadge() {
    const user = this.state.currentUser;
    if (!user) return;
    document.getElementById("nav-username").innerText = user.full_name || user.username;
    document.getElementById("nav-user-role").innerText = user.role.toUpperCase();
    document.getElementById("nav-avatar").innerText = user.username.substring(0, 2).toUpperCase();

    // Role-based visibility
    const isSuper = user.role === "superadmin";
    const isAdmin = user.role === "admin" || isSuper;
    const syncNav = document.getElementById("nav-item-sync");
    if (syncNav) syncNav.style.display = isAdmin ? "block" : "none";
    const userNav = document.getElementById("nav-item-users");
    if (userNav) userNav.style.display = isAdmin ? "block" : "none";
    const auditNav = document.getElementById("nav-item-audit");
    if (auditNav) auditNav.style.display = isAdmin ? "block" : "none";

    const btnAddUser = document.getElementById("btn-add-user-modal");
    if (btnAddUser) btnAddUser.style.display = isSuper ? "inline-flex" : "none";
  },

  showAddUserModal() {
    const isSuper = this.state.currentUser && this.state.currentUser.role === "superadmin";
    if (!isSuper) {
      alert("تنها مدیر ارشد (Superadmin) اجازه افزودن کاربر جدید را دارد.");
      return;
    }
    const form = document.getElementById("add-user-form");
    if (form) form.reset();
    const err = document.getElementById("add-user-error");
    if (err) {
      err.style.display = "none";
      err.innerText = "";
    }
    const modal = document.getElementById("add-user-modal");
    if (modal) modal.style.display = "flex";
  },

  hideAddUserModal() {
    const modal = document.getElementById("add-user-modal");
    if (modal) modal.style.display = "none";
  },

  showLoginModal() {
    document.getElementById("login-modal").style.display = "flex";
  },

  hideLoginModal() {
    document.getElementById("login-modal").style.display = "none";
  },

  showSetupModal() {
    document.getElementById("setup-modal").style.display = "flex";
  },

  hideSetupModal() {
    document.getElementById("setup-modal").style.display = "none";
  },

  bindEvents() {
    // Navigation
    document.querySelectorAll(".nav-link").forEach(link => {
      link.addEventListener("click", (e) => {
        const tab = e.currentTarget.getAttribute("data-tab");
        if (tab) this.switchTab(tab);
      });
    });

    // Theme & Lang toggles
    document.getElementById("theme-toggle-btn").addEventListener("click", () => {
      this.applyTheme(this.state.theme === "dark" ? "light" : "dark");
      if (this.state.activeTab === "dashboard") this.loadDashboardActivity();
    });

    document.getElementById("lang-toggle-btn").addEventListener("click", () => {
      this.applyLang(this.state.lang === "fa" ? "en" : "fa");
      this.loadCurrentTab();
    });

    // Logout
    document.getElementById("btn-logout").addEventListener("click", async () => {
      await fetch("/api/auth/logout", { credentials: "same-origin" });
      localStorage.removeItem("panel_token");
      this.state.token = null;
      this.state.currentUser = null;
      window.location.reload();
    });

    // Login Form Submit
    document.getElementById("login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const u = document.getElementById("login-username").value.trim();
      const p = document.getElementById("login-password").value;
      const errEl = document.getElementById("login-error");
      errEl.style.display = "none";

      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: u, password: p })
        });
        const data = await res.json();
        if (res.ok) {
          this.state.token = data.access_token;
          localStorage.setItem("panel_token", data.access_token);
          this.state.currentUser = data.user;
          this.renderUserBadge();
          this.hideLoginModal();
          this.loadCurrentTab();
        } else {
          errEl.innerText = data.detail || "خطا در احراز هویت";
          errEl.style.display = "block";
        }
      } catch (err) {
        errEl.innerText = "ارتباط با سرور برقرار نشد.";
        errEl.style.display = "block";
      }
    });

    // Initial Setup Form Submit
    document.getElementById("setup-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const u = document.getElementById("setup-username").value.trim();
      const p = document.getElementById("setup-password").value;
      const f = document.getElementById("setup-fullname").value.trim();
      const errEl = document.getElementById("setup-error");
      errEl.style.display = "none";

      try {
        const res = await fetch("/api/auth/initial-setup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: u, password: p, full_name: f })
        });
        const data = await res.json();
        if (res.ok) {
          alert("مدیر سیستم ایجاد شد. اکنون وارد شوید.");
          this.hideSetupModal();
          this.showLoginModal();
        } else {
          errEl.innerText = data.detail || "خطا در ایجاد مدیر";
          errEl.style.display = "block";
        }
      } catch (err) {
        errEl.innerText = "ارتباط با سرور برقرار نشد.";
        errEl.style.display = "block";
      }
    });

    // Add User Form Submission
    const addUserForm = document.getElementById("add-user-form");
    if (addUserForm) {
      addUserForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const errEl = document.getElementById("add-user-error");
        errEl.style.display = "none";

        const username = document.getElementById("add-user-username").value.trim();
        const fullName = document.getElementById("add-user-fullname").value.trim();
        const role = document.getElementById("add-user-role").value;
        const password = document.getElementById("add-user-password").value;
        const confirmPassword = document.getElementById("add-user-password-confirm").value;

        if (password !== confirmPassword) {
          errEl.innerText = "رمز عبور با تکرار آن مطابقت ندارد.";
          errEl.style.display = "block";
          return;
        }

        const submitBtn = document.getElementById("btn-submit-add-user");
        if (submitBtn) submitBtn.disabled = true;

        try {
          const res = await fetch("/api/panel-users", {
            method: "POST",
            headers: this.getAuthHeaders(),
            body: JSON.stringify({
              username: username,
              full_name: fullName,
              role: role,
              password: password
            })
          });

          if (res.ok) {
            alert("کاربر جدید با موفقیت ایجاد شد.");
            this.hideAddUserModal();
            this.loadUsers();
          } else {
            const data = await res.json();
            errEl.innerText = data.detail || "خطا در ایجاد کاربر";
            errEl.style.display = "block";
          }
        } catch (err) {
          errEl.innerText = "ارتباط با سرور برقرار نشد.";
          errEl.style.display = "block";
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });
    }

    // Quick Date Filters
    document.querySelectorAll(".btn-quick-date").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const type = e.currentTarget.getAttribute("data-range");
        const range = Jalali.getQuickRange(type);
        document.getElementById("filter-date-from").value = range.from;
        document.getElementById("filter-date-to").value = range.to;
        this.loadReports(1);
      });
    });

    // Report search & reset
    document.getElementById("btn-search-reports").addEventListener("click", () => this.loadReports(1));
    document.getElementById("btn-reset-reports").addEventListener("click", () => {
      document.getElementById("filter-username").value = "";
      document.getElementById("filter-hub").value = "";
      document.getElementById("filter-status").value = "";
      document.getElementById("filter-date-from").value = "";
      document.getElementById("filter-date-to").value = "";
      this.loadReports(1);
    });

    // Excel & CSV Export Buttons
    document.getElementById("btn-export-excel").addEventListener("click", () => this.exportReport("excel"));
    document.getElementById("btn-export-csv").addEventListener("click", () => this.exportReport("csv"));

    // Sync trigger
    document.getElementById("btn-run-sync").addEventListener("click", async () => {
      const btn = document.getElementById("btn-run-sync");
      btn.disabled = true;
      btn.innerText = "در حال پردازش...";
      try {
        const res = await fetch("/api/sync/run", {
          method: "POST",
          headers: this.getAuthHeaders()
        });
        const data = await res.json();
        alert(`همگام‌سازی پایان یافت.\nفایل‌های بررسی شده: ${data.files_checked}\nرویدادهای جدید: ${data.events_imported}`);
        this.loadSyncData();
      } catch (err) {
        alert("خطا در همگام‌سازی لاگ");
      } finally {
        btn.disabled = false;
        btn.innerText = this.t("triggerSync");
      }
    });
  },

  switchTab(tab) {
    const role = this.state.currentUser ? this.state.currentUser.role : null;
    const isAdmin = role === "superadmin" || role === "admin";
    if (["sync", "users", "audit"].includes(tab) && !isAdmin) {
      alert("شما دسترسی لازم برای مشاهده این بخش را ندارید.");
      return;
    }

    this.state.activeTab = tab;
    document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
    const activeNav = document.querySelector(`.nav-link[data-tab="${tab}"]`);
    if (activeNav) activeNav.classList.add("active");

    document.querySelectorAll(".tab-pane").forEach(p => p.style.display = "none");
    const targetPane = document.getElementById(`tab-${tab}`);
    if (targetPane) targetPane.style.display = "block";

    this.loadCurrentTab();
  },

  loadCurrentTab() {
    if (this.state.activeTab === "dashboard") {
      this.loadDashboard();
    } else if (this.state.activeTab === "reports") {
      this.loadReportsMeta();
      this.loadReports(1);
    } else if (this.state.activeTab === "sync") {
      this.loadSyncData();
    } else if (this.state.activeTab === "users") {
      this.loadUsers();
    } else if (this.state.activeTab === "audit") {
      this.loadAuditLogs(1);
    }
  },

  // -------------------------------------------------------------
  // Dashboard Logic
  // -------------------------------------------------------------
  async loadDashboard() {
    try {
      const [sumRes, topRes, recRes, qRes] = await Promise.all([
        fetch("/api/dashboard/summary", { headers: this.getAuthHeaders() }),
        fetch("/api/dashboard/top-users?limit=7", { headers: this.getAuthHeaders() }),
        fetch("/api/dashboard/recent-events?limit=8", { headers: this.getAuthHeaders() }),
        fetch("/api/dashboard/quality-report", { headers: this.getAuthHeaders() })
      ]);

      if (sumRes.ok) {
        const s = await sumRes.json();
        document.getElementById("stat-vpn-users").innerText = s.total_vpn_users;
        document.getElementById("stat-total-sessions").innerText = s.total_sessions;
        document.getElementById("stat-active-sessions").innerText = s.active_sessions;
        document.getElementById("stat-incomplete-sessions").innerText = s.incomplete_sessions;
        document.getElementById("stat-total-duration").innerText = s.total_duration_formatted;
      }

      if (qRes.ok) {
        const q = await qRes.json();
        document.getElementById("stat-accuracy").innerText = `${q.overall_confidence}%`;
      }

      if (topRes.ok) {
        const topUsers = await topRes.json();
        this.renderTopUsers(topUsers);
      }

      if (recRes.ok) {
        const recEvents = await recRes.json();
        this.renderRecentEvents(recEvents);
      }

      await this.loadDashboardActivity();
    } catch (e) {
      console.error("Dashboard error:", e);
    }
  },

  renderTopUsers(users) {
    const tbody = document.getElementById("top-users-tbody");
    if (!tbody) return;
    if (users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">داده‌ای یافت نشد</td></tr>`;
      return;
    }
    const esc = this.escapeHtml;
    tbody.innerHTML = users.map(u => `
      <tr>
        <td><strong>${esc(u.username)}</strong></td>
        <td>${esc(u.sessions_count)}</td>
        <td><span style="color:var(--accent-emerald); font-weight:600;">${esc(u.total_duration_formatted)}</span></td>
        <td>${this.state.lang === 'fa' ? esc(u.last_seen_jalali) : esc(u.last_seen)}</td>
        <td><code>${esc(u.last_ip)}</code></td>
      </tr>
    `).join("");
  },

  renderRecentEvents(events) {
    const tbody = document.getElementById("recent-events-tbody");
    if (!tbody) return;
    if (events.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">داده‌ای یافت نشد</td></tr>`;
      return;
    }
    const esc = this.escapeHtml;
    tbody.innerHTML = events.map(e => `
      <tr>
        <td>${this.state.lang === 'fa' ? esc(e.timestamp_jalali) : esc(e.timestamp)}</td>
        <td><span class="badge badge-active">${esc(e.event_type)}</span></td>
        <td><strong>${esc(e.username)}</strong></td>
        <td>${esc(e.virtual_hub)}</td>
        <td><code>${esc(e.client_ip)}</code></td>
        <td><small style="color:var(--text-dim);">${esc(e.session_id)}</small></td>
      </tr>
    `).join("");
  },

  async loadDashboardActivity() {
    try {
      const res = await fetch("/api/dashboard/activity-chart?days=14", { headers: this.getAuthHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      this.drawActivityChart(data);
    } catch (e) {
      console.error("Chart error:", e);
    }
  },

  drawActivityChart(data) {
    const canvas = document.getElementById("activity-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width = canvas.parentElement.clientWidth;
    const height = canvas.height = 240;

    ctx.clearRect(0, 0, width, height);
    if (!data || data.length === 0) {
      ctx.fillStyle = "#64748b";
      ctx.font = "13px Tahoma";
      ctx.textAlign = "center";
      ctx.fillText("اطلاعاتی برای نمایش نمودار وجود ندارد", width / 2, height / 2);
      return;
    }

    const padding = { top: 30, right: 30, bottom: 45, left: 50 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const maxVal = Math.max(...data.map(d => d.session_count), 5);
    const stepX = chartW / data.length;

    // Grid lines
    ctx.strokeStyle = this.state.theme === "dark" ? "#1e293b" : "#e2e8f0";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      // Axis label
      const val = Math.round(maxVal - (maxVal / 4) * i);
      ctx.fillStyle = "#64748b";
      ctx.font = "10px Tahoma";
      ctx.textAlign = "right";
      ctx.fillText(val, padding.left - 8, y + 3);
    }

    // Bars
    data.forEach((d, i) => {
      const barW = Math.max(stepX * 0.55, 12);
      const barH = (d.session_count / maxVal) * chartH;
      const x = padding.left + i * stepX + (stepX - barW) / 2;
      const y = padding.top + chartH - barH;

      // Gradient fill
      const grad = ctx.createLinearGradient(0, y, 0, y + barH);
      grad.addColorStop(0, "#3b82f6");
      grad.addColorStop(1, "rgba(59, 130, 246, 0.4)");

      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.roundRect(x, y, barW, barH, [4, 4, 0, 0]);
      ctx.fill();

      // Date label
      ctx.fillStyle = "#94a3b8";
      ctx.font = "10px Tahoma";
      ctx.textAlign = "center";
      const lbl = this.state.lang === "fa" ? d.date_jalali.substring(5) : d.date_gregorian.substring(5);
      ctx.fillText(lbl, x + barW / 2, height - 12);

      // Value label on top of bar
      if (d.session_count > 0) {
        ctx.fillStyle = "#f1f5f9";
        ctx.fillText(d.session_count, x + barW / 2, y - 6);
      }
    });
  },

  // -------------------------------------------------------------
  // Reports Logic
  // -------------------------------------------------------------
  async loadReportsMeta() {
    try {
      const [uRes, hRes] = await Promise.all([
        fetch("/api/sessions/usernames", { headers: this.getAuthHeaders() }),
        fetch("/api/sessions/hubs", { headers: this.getAuthHeaders() })
      ]);
      if (uRes.ok) {
        this.state.usernames = await uRes.json();
        const dl = document.getElementById("username-datalist");
        if (dl) dl.innerHTML = this.state.usernames.map(u => `<option value="${u}"></option>`).join("");
      }
      if (hRes.ok) {
        this.state.hubs = await hRes.json();
        const hubSel = document.getElementById("filter-hub");
        if (hubSel) {
          hubSel.innerHTML = `<option value="">همه هاب‌ها (All)</option>` +
            this.state.hubs.map(h => `<option value="${h}">${h}</option>`).join("");
        }
      }
    } catch (e) {
      console.error(e);
    }
  },

  async loadReports(page = 1) {
    this.state.reportPage = page;
    const user = document.getElementById("filter-username").value.trim();
    const hub = document.getElementById("filter-hub").value;
    const status = document.getElementById("filter-status").value;
    const from = document.getElementById("filter-date-from").value.trim();
    const to = document.getElementById("filter-date-to").value.trim();

    const params = new URLSearchParams({
      page: page,
      page_size: 25
    });
    if (user) params.append("username", user);
    if (hub) params.append("virtual_hub", hub);
    if (status) params.append("status", status);
    if (from) params.append("date_from", from);
    if (to) params.append("date_to", to);

    const tbody = document.getElementById("sessions-tbody");
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;">در حال دریافت اطلاعات...</td></tr>`;

    try {
      const res = await fetch(`/api/sessions?${params.toString()}`, { headers: this.getAuthHeaders() });
      if (!res.ok) return;
      const data = await res.json();

      this.renderReportSummary(data.summary);
      this.renderSessionsTable(data.items);
      this.renderPagination(data.page, data.total_pages, data.total_count);
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--accent-rose);">خطا در دریافت اطلاعات</td></tr>`;
    }
  },

  renderReportSummary(s) {
    if (!s) return;
    document.getElementById("sum-sessions-count").innerText = s.total_sessions;
    document.getElementById("sum-confirmed-duration").innerText = s.total_duration_formatted;
    document.getElementById("sum-avg-duration").innerText = s.avg_duration_formatted;
    document.getElementById("sum-max-duration").innerText = s.max_duration_formatted;
    document.getElementById("sum-incomplete-count").innerText = s.incomplete_sessions;
  },

  renderSessionsTable(items) {
    const tbody = document.getElementById("sessions-tbody");
    if (!items || items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:30px;">هیچ رکوردی منطبق با فیلترها یافت نشد.</td></tr>`;
      return;
    }

    const isFa = (this.state.lang === "fa");
    const esc = this.escapeHtml;
    tbody.innerHTML = items.map(s => {
      let badgeClass = "badge-incomplete";
      let statusName = s.status;
      let statusTitle = s.status_reason || "";

      if (s.status === "COMPLETED") {
        badgeClass = "badge-completed";
        statusName = isFa ? "تکمیل‌شده" : "Completed";
      } else if (s.status === "ACTIVE") {
        badgeClass = "badge-active";
        statusName = isFa ? "در حال اتصال (لاگ)" : "Active (In Log)";
        statusTitle = isFa 
          ? "نشست در جریان لاگ‌ها باز است و رویداد قطعی ثبت نشده است (استخراج غیرمستقیم از لاگ، نه سوکت زنده vpncmd)"
          : "Session opened in log stream with no disconnect event recorded yet (log-derived, not a live vpncmd socket check)";
      } else if (s.status === "UNVERIFIED") {
        badgeClass = "badge-unverified";
        statusName = isFa ? "نامشخص / تاییدنشده" : "Unverified";
      } else {
        badgeClass = "badge-incomplete";
        statusName = isFa ? "ناقص" : "Incomplete";
      }

      const loginStr = isFa ? s.login_time_jalali : s.login_time;
      const logoutStr = isFa ? s.logout_time_jalali : s.logout_time;

      return `
        <tr>
          <td><strong>${esc(s.username)}</strong></td>
          <td><span class="badge ${badgeClass}" title="${esc(statusTitle)}">${statusName}</span></td>
          <td>${esc(loginStr) || "-"}</td>
          <td>${esc(logoutStr) || "-"}</td>
          <td><strong>${esc(s.duration_formatted)}</strong></td>
          <td><code>${esc(s.client_ip)}</code></td>
          <td>${esc(s.virtual_hub)}</td>
          <td><small style="color:var(--text-dim);" title="${esc(s.status_reason) || ''}">${esc(s.session_id)}</small></td>
        </tr>
      `;
    }).join("");
  },

  renderPagination(page, totalPages, totalCount) {
    const container = document.getElementById("reports-pagination");
    if (!container) return;
    if (totalPages <= 1) {
      container.innerHTML = `<span style="color:var(--text-dim); font-size:12px;">مجموع رکوردهای منطبق: ${totalCount}</span>`;
      return;
    }

    container.innerHTML = `
      <div style="display:flex; align-items:center; justify-content:space-between; width:100%;">
        <span style="font-size:12px; color:var(--text-muted);">صفحه ${page} از ${totalPages} (کل رکوردها: ${totalCount})</span>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-secondary btn-sm" ${page <= 1 ? 'disabled' : ''} onclick="App.loadReports(${page - 1})">قبلی</button>
          <button class="btn btn-secondary btn-sm" ${page >= totalPages ? 'disabled' : ''} onclick="App.loadReports(${page + 1})">بعدی</button>
        </div>
      </div>
    `;
  },

  exportReport(type) {
    const user = document.getElementById("filter-username").value.trim();
    const hub = document.getElementById("filter-hub").value;
    const status = document.getElementById("filter-status").value;
    const from = document.getElementById("filter-date-from").value.trim();
    const to = document.getElementById("filter-date-to").value.trim();

    const params = new URLSearchParams({ lang: this.state.lang });
    if (user) params.append("username", user);
    if (hub) params.append("virtual_hub", hub);
    if (status) params.append("status", status);
    if (from) params.append("date_from", from);
    if (to) params.append("date_to", to);

    window.open(`/api/export/${type}?${params.toString()}`, "_blank");
  },

  // -------------------------------------------------------------
  // Log Sync Logic
  // -------------------------------------------------------------
  async loadSyncData() {
    try {
      const [stRes, dgRes] = await Promise.all([
        fetch("/api/sync/status", { headers: this.getAuthHeaders() }),
        fetch("/api/sync/diagnostics", { headers: this.getAuthHeaders() })
      ]);

      if (stRes.ok) {
        const data = await stRes.json();
        document.getElementById("sync-total-events").innerText = data.total_raw_events;
        document.getElementById("sync-total-sessions").innerText = data.total_sessions;
        const tbody = document.getElementById("tracked-files-tbody");
        if (tbody) {
          if (data.tracked_files.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;">هنوز فایلی ثبت نشده است.</td></tr>`;
          } else {
            tbody.innerHTML = data.tracked_files.map(f => `
              <tr>
                <td><code>${f.file_path.split(/[\\/]/).pop()}</code></td>
                <td>${f.last_byte_offset} bytes</td>
                <td>${f.last_line_number}</td>
                <td><span class="badge badge-completed">${f.status}</span></td>
                <td>${f.last_synced_at}</td>
              </tr>
            `).join("");
          }
        }
      }

      if (dgRes.ok) {
        const diag = await dgRes.json();
        const box = document.getElementById("diagnostics-box");
        let html = `
          <div style="margin-bottom:12px;"><strong>مسیر تنظیم‌شده:</strong> <code>${diag.configured_dir}</code></div>
          <div style="margin-bottom:8px;">وجود دایرکتوری: ${diag.dir_exists ? '✅ بله' : '❌ خیر'}</div>
          <div style="margin-bottom:8px;">دسترسی خواندن: ${diag.dir_readable ? '✅ مجاز' : '❌ غیرمجاز'}</div>
          <div style="margin-bottom:8px;">فایل‌های لاگ شناسایی‌شده: <strong>${diag.total_files}</strong></div>
          <div style="margin-bottom:8px;">لاگ سرور (server_log): ${diag.server_log_found ? '✅ یافت شد' : '⚠️ یافت نشد'}</div>
          <div style="margin-bottom:8px;">لاگ امنیتی هاب‌ها (security_log): ${diag.security_log_found ? '✅ یافت شد' : '⚠️ یافت نشد'}</div>
        `;
        if (diag.warnings.length > 0) {
          html += `<div style="margin-top:14px; color:var(--accent-amber);"><strong>هشدارها:</strong><ul>` +
            diag.warnings.map(w => `<li>${w}</li>`).join("") + `</ul></div>`;
        }
        if (diag.instructions.length > 0) {
          html += `<div style="margin-top:14px; color:var(--accent-blue);"><strong>راهنما:</strong><ul>` +
            diag.instructions.map(ins => `<li>${ins}</li>`).join("") + `</ul></div>`;
        }
        box.innerHTML = html;
      }
    } catch (e) {
      console.error(e);
    }
  },

  // -------------------------------------------------------------
  // Panel Users Logic
  // -------------------------------------------------------------
  async loadUsers() {
    try {
      const res = await fetch("/api/panel-users", { headers: this.getAuthHeaders() });
      if (!res.ok) return;
      const users = await res.json();
      const tbody = document.getElementById("panel-users-tbody");
      if (!tbody) return;

      const isSuper = this.state.currentUser && this.state.currentUser.role === "superadmin";
      const btnAddUser = document.getElementById("btn-add-user-modal");
      if (btnAddUser) btnAddUser.style.display = isSuper ? "inline-flex" : "none";

      const esc = this.escapeHtml;
      tbody.innerHTML = users.map(u => `
        <tr>
          <td><strong>${esc(u.username)}</strong></td>
          <td>${esc(u.full_name) || "-"}</td>
          <td><span class="badge badge-active">${esc(u.role)}</span></td>
          <td>${u.is_active ? 'فعال' : 'غیرفعال'}</td>
          <td>${esc(u.created_at)}</td>
          <td>${esc(u.last_login_at) || "-"}</td>
          <td>
            ${(isSuper || u.id === App.state.currentUser.id) ? `
              <button class="btn btn-secondary btn-sm" onclick="App.openResetPwd(${u.id}, '${esc(u.username)}')">رمز</button>
            ` : ''}
            ${(isSuper && u.id !== App.state.currentUser.id) ? `
              <button class="btn btn-danger btn-sm" onclick="App.deleteUser(${u.id}, '${esc(u.username)}')">حذف</button>
            ` : ''}
          </td>
        </tr>
      `).join("");
    } catch (e) {
      console.error(e);
    }
  },

  async deleteUser(id, username) {
    if (!confirm(`آیا از حذف کاربر '${username}' اطمینان دارید؟`)) return;
    try {
      const res = await fetch(`/api/panel-users/${id}`, {
        method: "DELETE",
        headers: this.getAuthHeaders()
      });
      if (res.ok) {
        alert("کاربر حذف شد.");
        this.loadUsers();
      } else {
        const d = await res.json();
        alert(d.detail || "خطا در حذف کاربر");
      }
    } catch (e) {
      alert("خطا در برقراری ارتباط");
    }
  },

  openResetPwd(id, username) {
    const newPwd = prompt(`رمز عبور جدید برای کاربر '${username}' را وارد کنید (حداقل ۸ کاراکتر):`);
    if (!newPwd) return;
    if (newPwd.length < 8) {
      alert("رمز عبور باید حداقل ۸ کاراکتر باشد.");
      return;
    }
    fetch(`/api/panel-users/${id}/reset-password`, {
      method: "POST",
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ new_password: newPwd })
    }).then(async res => {
      if (res.ok) alert("رمز عبور با موفقیت بروزرسانی شد.");
      else {
        const d = await res.json();
        alert(d.detail || "خطا در تغییر رمز عبور");
      }
    });
  },

  // -------------------------------------------------------------
  // Audit Logs Logic
  // -------------------------------------------------------------
  async loadAuditLogs(page = 1) {
    this.state.auditPage = page;
    try {
      const res = await fetch(`/api/audit-logs?page=${page}&page_size=25`, { headers: this.getAuthHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      const tbody = document.getElementById("audit-tbody");
      if (!tbody) return;

      const esc = this.escapeHtml;
      tbody.innerHTML = data.items.map(a => `
        <tr>
          <td>${this.state.lang === 'fa' ? esc(a.created_at_jalali) : esc(a.created_at)}</td>
          <td><strong>${esc(a.username)}</strong></td>
          <td><span class="badge badge-active">${esc(a.action)}</span></td>
          <td>${esc(a.details)}</td>
          <td><code>${esc(a.ip_address)}</code></td>
        </tr>
      `).join("");
    } catch (e) {
      console.error(e);
    }
  }
};

window.addEventListener("DOMContentLoaded", () => App.init());
