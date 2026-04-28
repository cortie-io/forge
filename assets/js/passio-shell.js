(() => {
  const path = window.location.pathname || "";
  const route = path.split("/").pop() || "index.html";
  const routeClass = `passio-route-${route.replace(/[^a-z0-9]/gi, "-").toLowerCase()}`;

  const DEFAULT_NAV_GROUPS = [
    {
      label: "Product",
      items: [
        { name: "Cortie Home", href: "https://cortie.io/", desc: "Brand overview and latest highlights." },
        { name: "Services Overview", href: "https://cortie.io/services", desc: "Service portfolio and operating model." },
        { name: "Works", href: "https://cortie.io/works", desc: "Delivery tracks and product outcomes." },
        { name: "Lab", href: "https://cortie.io/lab", desc: "Experiments, validation, and launch loops." }
      ]
    },
    {
      label: "Services",
      items: [
        { name: "Passio", href: "https://passio.cortie.io/pages/index.html", desc: "Exam and certification learning workspace." },
        { name: "Afinder", href: "https://afinder.cortie.io/", desc: "Academic record and feedback service." },
        { name: "Auth Server", href: "https://auth.cortie.io/", desc: "Central SSO login and session authority." }
      ]
    },
    {
      label: "Developers",
      items: [
        { name: "Docs", href: "https://cortie.io/docs", desc: "Integration guides and implementation docs." },
        { name: "API Center", href: "https://cortie.io/api", desc: "API modules, references, and examples." },
        { name: "Developer Console", href: "https://cortie.io/developers", desc: "Keys, admin tools, and release utilities." },
        { name: "Changelog", href: "https://cortie.io/changelog", desc: "Recent platform and service updates." }
      ]
    },
    {
      label: "Company",
      items: [
        { name: "About", href: "https://cortie.io/about", desc: "Brand mission and execution narrative." },
        { name: "Status", href: "https://cortie.io/status", desc: "Live service health and uptime summary." },
        { name: "Contact", href: "https://cortie.io/contact", desc: "Partnership and project collaboration." }
      ]
    }
  ];

  const SHARED_NAV_CONFIG_JS = "https://cortie.io/assets/cortie-nav-config.js?v=20260425-navsync4";
  const currentAbsUrl = window.location.href;
  const loginUrl = `https://auth.cortie.io/login?redirect_uri=${encodeURIComponent(currentAbsUrl)}`;
  const signupUrl = `https://auth.cortie.io/signup?redirect_uri=${encodeURIComponent(currentAbsUrl)}`;
  const logoutUrl = `https://auth.cortie.io/logout?redirect_uri=${encodeURIComponent(currentAbsUrl)}`;

  const NAV_HTML = `
    <nav class="n-nav" aria-label="Cortie navigation">
      <a href="https://cortie.io" class="n-logo">
        <img src="/assets/shape_logo.svg?v=20260425fix3" alt="cortie symbol" class="brand-mark">
        <img src="/assets/text_logo.svg?v=20260425fix3" alt="cortie" class="brand-text">
        <span class="n-service-sep">|</span>
        <span class="n-service">PASSIO</span>
      </a>
      <ul class="n-links" id="n-links"></ul>
      <div class="n-actions" id="n-actions">
        <a href="${loginUrl}" class="n-login">Log in</a>
        <a href="${signupUrl}" class="n-start">Get started</a>
      </div>
    </nav>
    <div class="n-mega" id="n-mega" style="display:none;">
      <div class="n-mega-inner">
        <div class="n-mega-head"><p id="n-mega-title">Product</p><span>Explore sections in this category</span></div>
        <ul class="n-mega-list" id="n-mega-list"></ul>
      </div>
    </div>
  `;

  const SUBNAV_ITEMS = [
    { label: "Dashboard", href: "/pages/dashboard.html" },
    { label: "Question Bank", href: "/pages/question-bank.html" },
    { label: "History", href: "/pages/history.html" },
    { label: "AI Explain", href: "/pages/ai-explain.html" },
    { label: "API Guide", href: "/pages/api-guide.html" },
    { label: "API Token", href: "/pages/api-token.html" }
  ];

  const FOOTER_HTML = `
    <footer class="rich-footer">
      <div class="rich-footer-top">
        <div class="rich-footer-brand">
          <a href="/" class="n-logo">
            <img src="/assets/shape_logo.svg?v=20260425fix3" alt="cortie symbol" class="brand-mark">
            <img src="/assets/text_logo.svg?v=20260425fix3" alt="cortie" class="brand-text">
          </a>
          <p>Cortie is an AI-first software brand focused on execution, web usability, and network-aware reliability.</p>
        </div>
        <div class="rich-footer-col">
          <h4>Platform</h4>
          <a href="https://cortie.io/about">About</a>
          <a href="https://cortie.io/services">Services</a>
          <a href="https://cortie.io/works">Works</a>
          <a href="https://cortie.io/lab">Lab</a>
        </div>
        <div class="rich-footer-col">
          <h4>Developers</h4>
          <a href="https://cortie.io/docs">Docs</a>
          <a href="https://cortie.io/api">API Center</a>
          <a href="https://cortie.io/api/auth">Auth API</a>
          <a href="https://cortie.io/developers">Developer Console</a>
          <a href="https://cortie.io/changelog">Changelog</a>
          <a href="https://cortie.io/contact">Integration Support</a>
        </div>
        <div class="rich-footer-col">
          <h4>Operating Status</h4>
          <div class="rich-status"><i></i>Auth Service · Operational</div>
          <div class="rich-status"><i></i>Main Web · Operational</div>
          <div class="rich-status"><i></i>Session Exchange · Healthy</div>
        </div>
      </div>
      <div class="rich-footer-bottom">
        <div class="rich-copy">© 2026 CORTIE · ALL RIGHTS RESERVED</div>
        <div class="rich-copy">01 · CONTACT · CAREERS · PRIVACY · TERMS</div>
      </div>
    </footer>
  `;

  const style = document.createElement("style");
  style.id = "passio-shell-global-v3";
  style.textContent = `
  @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700;800&display=swap');
  body.passio-shellized, body.passio-shellized *{font-family:"Geist",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif!important}
  body.passio-shellized{background:#f8f9f5;color:#272829;padding-top:112px!important}
  body.passio-shellized header.nav, body.passio-shellized nav.nav, body.passio-shellized .cortie-global-nav{display:none!important}
  body.passio-shellized .page{padding-top:0!important}
  .n-nav{position:fixed;inset:0 0 auto 0;z-index:200;height:68px;display:flex;align-items:center;justify-content:space-between;padding:0 42px;background:#f8f9f5ea;backdrop-filter:blur(16px);border-bottom:1px solid rgba(39,40,41,.08)}
  .n-logo{display:flex;align-items:center;gap:1px;text-decoration:none;color:inherit}
  .n-nav .brand-mark{height:37px!important;width:auto!important}.n-nav .brand-text{height:28px!important;width:auto!important;margin-left:0}
  .n-service-sep{font-size:13px;color:#b8bec8;margin:0 6px 0 7px}.n-service{font-size:14px;font-weight:700;letter-spacing:.06em;color:#64748b}
  .p-subnav{position:fixed;left:0;right:0;top:68px;z-index:190;height:44px;display:flex;align-items:center;border-bottom:1px solid rgba(39,40,41,.08);background:#ffffffeb;backdrop-filter:blur(8px)}
  .p-subnav-inner{max-width:1400px;width:100%;margin:0 auto;padding:0 42px;display:flex;gap:8px;align-items:center;overflow:auto}
  .p-subnav-link{display:inline-flex;align-items:center;height:30px;padding:0 12px;border-radius:999px;font-size:12px;font-weight:600;color:#5b6472;border:1px solid transparent;text-decoration:none;white-space:nowrap}
  .p-subnav-link:hover{background:#eef1ec;border-color:#dde4d8;color:#1f2937}
  .p-subnav-link.active{background:#272829;color:#fff;border-color:#272829}
  .n-links{display:flex;gap:26px;list-style:none}
  .n-group-btn{font-family:inherit;background:none;border:none;color:#5c6270;font-size:13px;font-weight:400;cursor:pointer}
  .n-group-btn:hover,.n-group-btn.active{color:#2e333d}
  .n-actions{display:flex;gap:10px;align-items:center}
  .n-user{color:#525a67;font-size:13px}.n-login{font-size:12px;font-weight:400;color:#616878;padding:0 8px;background:none;border:none;cursor:pointer}
  .n-start{font-size:12px;font-weight:500;color:#fff;background:#272829;padding:9px 16px;border-radius:999px;text-decoration:none}.n-start:hover{background:#3D8E72}
  .n-mega{position:fixed;top:68px;left:0;right:0;z-index:201;border-bottom:1px solid rgba(39,40,41,.08);background:#fffffffa;backdrop-filter:blur(10px)}
  .n-mega-inner{max-width:1400px;margin:0 auto;padding:16px 42px 18px}.n-mega-head{display:flex;gap:10px;margin-bottom:12px}.n-mega-head p{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#667085}.n-mega-head span{font-size:12px;color:#808694}
  .n-mega-list{list-style:none;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px 24px}.n-mega-link{display:flex;flex-direction:column;gap:2px;padding:8px 0;border-bottom:1px solid rgba(220,224,229,.6);text-decoration:none;color:inherit}.n-mega-link strong{font-size:14px;font-weight:600}.n-mega-link span{font-size:12px;color:#525a67;line-height:1.6}
  .rich-footer{border-top:1px solid rgba(39,40,41,.08)!important;background:#fff!important;padding:42px 32px 22px!important}
  .rich-footer .brand-mark{height:20px}.rich-footer .brand-text{height:14px}
  .rich-footer-top{max-width:1680px!important;margin:0 auto!important;display:grid!important;grid-template-columns:1.45fr 1fr 1fr 1fr!important;gap:72px!important}
  .rich-footer-brand p{margin-top:14px!important;max-width:420px!important;font-size:12px!important;line-height:1.72!important;color:#6b7280!important}
  .rich-footer-col h4{margin-bottom:10px!important;font-size:9px!important;letter-spacing:.22em!important;color:#6b7280!important;text-transform:uppercase}
  .rich-footer-col a{display:block;margin-bottom:7px!important;font-size:11px!important;line-height:1.35!important;color:#374151!important;text-decoration:none}
  .rich-status{margin-bottom:7px!important;font-size:11px!important;color:#374151!important;display:flex;align-items:center;gap:8px}
  .rich-status i{width:7px;height:7px;border-radius:50%;background:#86efac;display:inline-block;box-shadow:0 0 0 3px rgba(134,239,172,.22)}
  .rich-footer-bottom{max-width:1680px!important;margin:18px auto 0!important;padding-top:14px!important;border-top:1px solid #e5e7eb!important;display:flex!important;justify-content:space-between!important;gap:12px!important}
  .rich-copy{font-size:9px!important;letter-spacing:.16em!important;color:#9ca3af!important;text-transform:uppercase}
  .card,.panel,.subject-card,.history-card,.result-shell,.quiz-card,.admin-table-wrap,.api-doc-card,.cert-card,.step,.ri,.q-card,.score-card,.login-card{background:#fff!important;border:1px solid rgba(39,40,41,.08)!important;border-radius:18px!important;box-shadow:0 8px 22px rgba(23,30,43,.05)!important}
  .shell{max-width:1180px;margin:0 auto;padding:0 28px}
  .hero{padding:24px 0 30px;display:grid;grid-template-columns:1.1fr .9fr;gap:28px;align-items:start}
  .eyebrow{font-size:10px;letter-spacing:.11em;color:#7b8492;text-transform:uppercase}
  .hero h1{margin-top:10px;font-size:clamp(38px,4.2vw,58px);line-height:1.1;letter-spacing:-.03em;font-weight:300}
  .hero p{margin-top:12px;max-width:58ch;font-size:15px;line-height:1.75;color:#5b6472}
  .hero-actions{margin-top:18px;display:flex;gap:8px;flex-wrap:wrap}
  .btn-dark,.btn-light{padding:10px 16px;border-radius:999px;font-size:13px;font-weight:600;border:1px solid transparent;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}
  .btn-dark{background:#272829;color:#fff}.btn-dark:hover{background:#3D8E72}
  .btn-light{background:#fff;border-color:#d8ddd4;color:#374151}.btn-light:hover{background:#f4f6f2}
  .kpi-title{font-size:12px;color:#64748b;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
  .kpi-grid{margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .kpi{border:1px solid #e4e8e0;border-radius:12px;padding:12px;background:#fafbf9}
  .kpi strong{display:block;font-size:24px;line-height:1.1;font-weight:300;color:#272829}
  .kpi span{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#80889a}
  .kpi-wrap{background:#fff;border:1px solid rgba(39,40,41,.08);border-radius:16px;padding:16px}
  .timeline{margin-top:12px;display:grid;gap:10px}
  .t-row{display:grid;grid-template-columns:96px 1fr;gap:14px;padding:10px 0;border-bottom:1px solid #e6e9e2}
  .t-step{font-size:11px;letter-spacing:.1em;color:#7b8492}
  .t-desc h4{font-size:18px;font-weight:600;color:#272829}.t-desc p{margin-top:4px;color:#5f6876;line-height:1.65;font-size:14px}
  .block{padding:12px 0 48px}
  .block h2{font-size:clamp(28px,3.2vw,42px);letter-spacing:-.022em;font-weight:300}
  .block .lead{margin-top:8px;max-width:64ch;color:#5b6472;line-height:1.75}
  .grid{margin-top:16px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
  .tile{background:#fff;border:1px solid #e5e9e1;border-radius:14px;padding:15px}
  .tile .num{font-size:10px;letter-spacing:.1em;color:#7b8391}
  .tile h3{margin-top:8px;font-size:20px;font-weight:600;color:#272829}
  .tile p{margin-top:6px;color:#5b6472;font-size:14px;line-height:1.65}
  .dash-chip{display:inline-flex;align-items:center;height:24px;padding:0 8px;border-radius:999px;background:#eef1ec;color:#4b5563;font-size:11px}
  main, .container.section, .screen, .quiz-layout{max-width:min(1240px,100% - 44px)!important;margin-left:auto!important;margin-right:auto!important}
  .container.section, .quiz-layout{padding-top:34px!important;padding-bottom:56px!important}
  h1,h2,h3{font-weight:500!important;letter-spacing:-.02em!important}
  p,.muted{color:#5f6876!important;line-height:1.7!important}
  .btn,.btn-sm,.btn-navy,.btn-out,.btn.primary,.btn.ghost{border-radius:999px!important}

  body.passio-route-dashboard-html .dash-shell{display:grid!important;grid-template-columns:.95fr 1.05fr!important;gap:18px!important}
  body.passio-route-dashboard-html .dash-headline{background:#fff;border:1px solid rgba(39,40,41,.08);border-radius:20px;padding:22px}
  body.passio-route-dashboard-html .subject-grid{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px!important}
  body.passio-route-dashboard-html .subject-card{padding:14px!important}

  body.passio-route-question-bank-html .qb-layout, body.passio-route-question-bank-html .question-bank-layout{display:grid!important;grid-template-columns:320px 1fr!important;gap:14px!important}
  body.passio-route-question-bank-html .filter-card, body.passio-route-question-bank-html .qb-side{position:sticky!important;top:92px!important;align-self:start}

  body.passio-route-history-html .history-grid, body.passio-route-history-html .history-list{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px!important}
  body.passio-route-history-html .history-revamp{display:grid;gap:18px}
  body.passio-route-history-html .history-summary{display:grid;grid-template-columns:1.2fr .8fr;gap:12px}
  body.passio-route-history-html .history-stat-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
  body.passio-route-history-html .history-stat{padding:14px;border:1px solid #e5e9e1;border-radius:14px;background:#fff}
  body.passio-route-history-html .history-stat strong{display:block;font-size:24px;font-weight:300;color:#272829;line-height:1.1}
  body.passio-route-history-html .history-stat span{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#7b8492}
  body.passio-route-history-html .history-quick{display:flex;gap:8px;flex-wrap:wrap}
  body.passio-route-history-html .history-columns{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  body.passio-route-history-html .history-column-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}
  body.passio-route-history-html .history-column-head h3{font-size:18px;font-weight:600}
  body.passio-route-history-html .history-empty{padding:22px;text-align:center}

  body.passio-route-quiz-html .quiz-layout,
  body.passio-route-quiz-detail-html .quiz-layout,
  body.passio-route-quiz-attempt-html .quiz-layout,
  body.passio-route-rag-detail-html .quiz-layout{max-width:min(1180px,100% - 34px)!important}
  body.passio-route-quiz-html .question-card,
  body.passio-route-quiz-detail-html .question-card,
  body.passio-route-quiz-attempt-html .question-card{padding:18px!important}
  body.passio-route-quiz-html #result-list,
  body.passio-route-quiz-detail-html #result-list,
  body.passio-route-quiz-attempt-html #result-list{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px!important}

  body.passio-route-api-guide-html .api-doc-wrap,
  body.passio-route-api-token-html .api-doc-wrap{display:grid!important;grid-template-columns:300px 1fr!important;gap:16px!important}
  body.passio-route-api-guide-html .api-side,
  body.passio-route-api-token-html .api-side{position:sticky!important;top:92px!important;align-self:start}

  body.passio-route-ai-explain-html .explain-grid,
  body.passio-route-ai-loading-html .explain-grid{display:grid!important;grid-template-columns:1fr 1fr!important;gap:12px!important}

  body.passio-route-admin-html .admin-shell{max-width:min(1380px,100% - 36px)!important;margin:0 auto}
  body.passio-route-admin-html .admin-toolbar{display:flex!important;justify-content:space-between!important;gap:10px!important;flex-wrap:wrap!important}
  body.passio-route-admin-html .admin-table-wrap{overflow:auto;border-radius:16px!important}

  body.passio-route-login-html main, body.passio-route-signup-html main{display:grid!important;place-items:center!important;min-height:calc(100vh - 68px)!important;padding:28px 16px 56px!important}
  body.passio-route-login-html .login-card, body.passio-route-signup-html .login-card{width:min(560px,100%)!important;padding:24px!important;border-radius:22px!important}

  @media(max-width:980px){.n-links{display:flex;gap:8px;overflow-x:auto;white-space:nowrap;max-width:48vw}.n-nav{height:62px;padding:0 14px}.n-nav .brand-mark{height:30px!important}.n-nav .brand-text{height:23px!important}.n-logo{gap:1px}.n-service-sep{font-size:10px;margin:0 5px}.n-service{font-size:11px}.n-mega{top:62px}.p-subnav{top:62px}.p-subnav-inner{padding:0 14px}.rich-footer{padding:30px 18px 16px!important}.rich-footer-top{grid-template-columns:1fr 1fr!important;gap:18px!important}}
  @media(max-width:980px){.shell{padding:0 18px}.hero{grid-template-columns:1fr}.grid{grid-template-columns:1fr}}
  @media(max-width:980px){body.passio-route-dashboard-html .dash-shell,body.passio-route-question-bank-html .qb-layout,body.passio-route-question-bank-html .question-bank-layout,body.passio-route-api-guide-html .api-doc-wrap,body.passio-route-api-token-html .api-doc-wrap{grid-template-columns:1fr!important}body.passio-route-history-html .history-grid,body.passio-route-history-html .history-list,body.passio-route-history-html .history-summary,body.passio-route-history-html .history-stat-grid,body.passio-route-history-html .history-columns,body.passio-route-quiz-html #result-list,body.passio-route-quiz-detail-html #result-list,body.passio-route-quiz-attempt-html #result-list,body.passio-route-ai-explain-html .explain-grid,body.passio-route-ai-loading-html .explain-grid{grid-template-columns:1fr!important}}
  @media(max-width:620px){.rich-footer-top{grid-template-columns:1fr!important}}
  `;
  document.head.appendChild(style);
  document.body.classList.add("passio-shellized");
  document.body.classList.add(routeClass);

  const navRoot = document.querySelector(".n-nav");
  if (!navRoot) {
    document.body.insertAdjacentHTML("afterbegin", NAV_HTML);
  }

  if (!document.querySelector(".p-subnav")) {
    const subnavHtml = `
      <nav class="p-subnav" aria-label="Passio service navigation">
        <div class="p-subnav-inner">
          ${SUBNAV_ITEMS.map((item) => `<a class="p-subnav-link" href="${item.href}" data-subnav-href="${item.href}">${item.label}</a>`).join("")}
        </div>
      </nav>
    `;
    const rootNav = document.querySelector(".n-nav");
    if (rootNav) rootNav.insertAdjacentHTML("afterend", subnavHtml);
  }

  const currentPath = window.location.pathname;
  document.querySelectorAll(".p-subnav-link").forEach((link) => {
    if (currentPath === link.dataset.subnavHref) {
      link.classList.add("active");
    }
  });

  const wireDashboardActions = async () => {
    const startBtn = document.getElementById("start-btn");
    const userName = document.getElementById("user-name");
    const avatar = document.getElementById("ava-dash");
    const adminBtn = document.getElementById("btn-admin-entry");

    if (startBtn) {
      startBtn.addEventListener("click", () => {
        const quizId = (window.crypto?.randomUUID && window.crypto.randomUUID()) || `quiz-${Date.now().toString(36)}`;
        sessionStorage.setItem("selectedSubject", "network-admin-2");
        sessionStorage.setItem("activeQuizId", quizId);
        location.href = `/pages/quiz.html?quizId=${encodeURIComponent(quizId)}`;
      });
    }

    try {
      const response = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json();
      const name = payload.user?.name || payload.user?.username || "Learner";
      if (userName) userName.textContent = name;
      if (avatar) avatar.textContent = name;

      let isAdmin = Boolean(payload.user?.isAdmin) || String(payload.user?.username || "").toLowerCase() === "deamon";
      if (!isAdmin) {
        try {
          const adminRes = await fetch("/api/admin/me", { credentials: "same-origin", cache: "no-store" });
          if (adminRes.ok) {
            const adminJson = await adminRes.json();
            isAdmin = Boolean(adminJson?.ok) && Boolean(adminJson?.user?.isAdmin);
          }
        } catch (_err) {}
      }
      if (adminBtn) adminBtn.style.display = isAdmin ? "inline-flex" : "none";
    } catch (_err) {}
  };

  const rebuildDashboardLayout = () => {
    if (!document.body.classList.contains("passio-route-dashboard-html")) return;
    const main = document.querySelector("main.container.section");
    if (!main) return;

    const cards = [...document.querySelectorAll(".subject-card")].map((card, idx) => {
      const title = card.querySelector(".subject-title")?.textContent?.trim() || `Track ${idx + 1}`;
      const desc = card.querySelector(".muted")?.textContent?.trim() || "Certification module";
      const tags = [...card.querySelectorAll(".dash-chip")].map((tag) => tag.textContent.trim()).slice(0, 2);
      const open = card.classList.contains("active");
      return { title, desc, tags, open };
    });

    main.className = "shell";
    main.innerHTML = `
      <section class="hero" style="padding-top:32px">
        <div>
          <div class="eyebrow">SUBJECT DASHBOARD</div>
          <h1><span id="user-name">Learner</span>, choose your next pass track.</h1>
          <p>Passio dashboard is rebuilt to match the home surface system: calmer spacing, clearer hierarchy, and module cards that scale cleanly as services expand.</p>
          <div class="hero-actions">
            <button class="btn-dark" id="start-btn">Start core track</button>
            <a class="btn-light" href="/pages/question-bank.html">Browse question bank</a>
            <a class="btn-light" id="btn-admin-entry" href="/pages/admin.html" style="display:none;">Admin console</a>
          </div>
          <div class="kpi-grid" style="margin-top:16px;max-width:560px">
            <div class="kpi"><strong>50</strong><span>questions / set</span></div>
            <div class="kpi"><strong>AI</strong><span>explain on demand</span></div>
            <div class="kpi"><strong>6</strong><span>active tracks</span></div>
            <div class="kpi"><strong id="ava-dash">Learner</strong><span>current learner</span></div>
          </div>
        </div>
        <aside class="kpi-wrap">
          <div class="kpi-title">Learning Notes</div>
          <div class="timeline">
            <div class="t-row"><div class="t-step">STEP 01</div><div class="t-desc"><h4>Pick one track</h4><p>Start from the active certification module and complete one full set.</p></div></div>
            <div class="t-row"><div class="t-step">STEP 02</div><div class="t-desc"><h4>Review weak points</h4><p>Use AI explain and question bank to reinforce missed concepts.</p></div></div>
            <div class="t-row"><div class="t-step">STEP 03</div><div class="t-desc"><h4>Repeat with pace</h4><p>Track attempts in history and iterate with focused sessions.</p></div></div>
          </div>
        </aside>
      </section>
      <section class="block" style="padding-top:10px">
        <h2>Certification modules</h2>
        <p class="lead">Cards are reorganized in a clean two-column grid that follows the home layout rhythm.</p>
        <div class="grid" style="grid-template-columns:repeat(2,minmax(0,1fr));margin-top:14px">
          ${cards
            .map(
              (item, idx) => `
            <article class="tile" style="padding:16px;border-radius:16px">
              <div class="num">${item.open ? "OPEN" : "SOON"}</div>
              <h3>${item.title}</h3>
              <p>${item.desc}</p>
              <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">
                ${item.tags.map((tag) => `<span class="dash-chip">${tag}</span>`).join("")}
              </div>
              <div style="margin-top:12px">
                ${
                  idx === 0
                    ? `<button class="btn-dark" id="start-btn-card" style="width:100%">Start this track</button>`
                    : `<button class="btn-light" style="width:100%" disabled>Preparing</button>`
                }
              </div>
            </article>`
            )
            .join("")}
        </div>
      </section>
    `;
  };

  const rebuildHistoryLayout = () => {
    if (!document.body.classList.contains("passio-route-history-html")) return false;
    const main = document.querySelector("main");
    if (!main || main.dataset.passioHistoryRebuilt === "1") return true;
    main.dataset.passioHistoryRebuilt = "1";
    main.className = "shell";
    main.innerHTML = `
      <section class="hero" style="padding-top:28px">
        <div>
          <div class="eyebrow">HISTORY</div>
          <h1>Learning records, rebuilt for fast review.</h1>
          <p>Track quiz attempts and AI explanation jobs in one cleaner workspace with less clutter and clearer scan hierarchy.</p>
          <div class="history-quick" style="margin-top:14px">
            <a class="btn-dark" href="/pages/dashboard.html">Start Quiz</a>
            <a class="btn-light" href="/pages/ai-explain.html">New AI Explain</a>
          </div>
        </div>
        <aside class="kpi-wrap">
          <div class="kpi-title">Learner Context</div>
          <div class="timeline">
            <div class="t-row"><div class="t-step">USER</div><div class="t-desc"><h4 id="user-name">Learner</h4><p>Recent activity from your account appears here in realtime.</p></div></div>
            <div class="t-row"><div class="t-step">SYNC</div><div class="t-desc"><h4>Auto refresh enabled</h4><p>Newest records are merged continuously without losing older pages.</p></div></div>
          </div>
        </aside>
      </section>
      <section class="block" style="padding-top:8px">
        <div class="history-revamp">
          <div class="history-summary">
            <article class="history-stat"><strong id="history-quiz-count">--</strong><span>Quiz Attempts</span></article>
            <div class="history-stat-grid">
              <article class="history-stat"><strong id="history-rag-count">--</strong><span>AI Jobs</span></article>
              <article class="history-stat"><strong>Live</strong><span>Refresh</span></article>
              <article class="history-stat"><strong>Unified</strong><span>Layout</span></article>
            </div>
          </div>
          <div class="history-columns">
            <section class="tile" style="padding:16px">
              <div class="history-column-head">
                <h3>Quiz Attempts</h3>
                <button type="button" class="btn-light" id="btn-quiz-history-more" style="display:none">Load older</button>
              </div>
              <section id="quiz-history-list" class="history-list"></section>
              <section id="quiz-history-empty" class="card history-empty" style="display:none">No quiz history yet.</section>
            </section>
            <section class="tile" style="padding:16px">
              <div class="history-column-head">
                <h3>AI Explain Jobs</h3>
                <button type="button" class="btn-light" id="btn-rag-history-more" style="display:none">Load older</button>
              </div>
              <section id="rag-history-list" class="history-list"></section>
              <section id="rag-history-empty" class="card history-empty" style="display:none">No AI explanation history yet.</section>
            </section>
          </div>
        </div>
      </section>
    `;
    return true;
  };

  const rebuildGenericPageLayout = () => {
    if (document.body.classList.contains("passio-route-index-html") || document.body.classList.contains("passio-route-dashboard-html")) {
      return;
    }
    const main = document.querySelector("main");
    if (!main || main.dataset.passioRebuilt === "1") return;
    main.dataset.passioRebuilt = "1";

    const pageMeta = {
      "question-bank.html": { eyebrow: "QUESTION BANK", title: "Curate better questions with a cleaner workspace.", lead: "A reorganized surface for filter-first exploration and targeted practice." },
      "history.html": { eyebrow: "HISTORY", title: "Track attempts with clearer learning momentum.", lead: "Past sessions, outcomes, and AI follow-ups in one structured view." },
      "quiz.html": { eyebrow: "QUIZ SESSION", title: "Focus mode for high-quality attempts.", lead: "Reduced visual noise and stronger hierarchy for problem solving." },
      "quiz-detail.html": { eyebrow: "QUIZ DETAIL", title: "Understand each question with contextual review.", lead: "A calmer detail layout aligned with Passio home rhythm." },
      "quiz-attempt.html": { eyebrow: "QUIZ ATTEMPT", title: "Review attempt data with stronger readability.", lead: "Step-by-step result flow and explanation blocks in a unified shell." },
      "rag-detail.html": { eyebrow: "AI REVIEW", title: "AI detail view rebuilt for comprehension first.", lead: "Explanation flow and feedback blocks now follow the same product cadence." },
      "api-guide.html": { eyebrow: "API GUIDE", title: "Developer docs in a cleaner delivery format.", lead: "Structured sections and stable spacing for faster integration scanning." },
      "api-token.html": { eyebrow: "API TOKEN", title: "Token operations in a focused utility layout.", lead: "Operational controls and metadata organized for daily use." },
      "ai-explain.html": { eyebrow: "AI EXPLAIN", title: "AI explanation page aligned to home design system.", lead: "Reading comfort, section rhythm, and actionable hierarchy improved." },
      "ai-loading.html": { eyebrow: "AI PROCESS", title: "Processing state with clearer status communication.", lead: "Loading and queue states now match the global product mood." },
      "admin.html": { eyebrow: "ADMIN", title: "Admin surface rebuilt for operational clarity.", lead: "Table-heavy workflows framed in a calmer, scalable layout." },
      "login.html": { eyebrow: "AUTH", title: "Sign in through a cleaner entry surface.", lead: "A full-shell authentication layout aligned with the main product tone." },
      "signup.html": { eyebrow: "AUTH", title: "Create your account in a unified experience.", lead: "The registration flow now follows Passio home composition language." }
    };

    const key = (window.location.pathname.split("/").pop() || "").toLowerCase();
    const meta = pageMeta[key] || { eyebrow: "PASSIO", title: "Unified page layout", lead: "This page now follows the same base composition as home." };

    const preserved = document.createElement("div");
    preserved.className = "passio-generic-content";
    while (main.firstChild) preserved.appendChild(main.firstChild);

    main.className = "shell";
    main.innerHTML = `
      <section class="hero" style="padding-top:28px">
        <div>
          <div class="eyebrow">${meta.eyebrow}</div>
          <h1>${meta.title}</h1>
          <p>${meta.lead}</p>
        </div>
        <aside class="kpi-wrap">
          <div class="kpi-title">Page Context</div>
          <div class="timeline">
            <div class="t-row"><div class="t-step">FLOW 01</div><div class="t-desc"><h4>Structured surface</h4><p>Core controls and content blocks are grouped into a consistent shell.</p></div></div>
            <div class="t-row"><div class="t-step">FLOW 02</div><div class="t-desc"><h4>Readable density</h4><p>Spacing, typography, and card rhythm are aligned with home composition.</p></div></div>
          </div>
        </aside>
      </section>
      <section class="block" style="padding-top:8px">
        <div class="tile" style="padding:18px;border-radius:16px">
          <div id="passio-generic-content-slot"></div>
        </div>
      </section>
    `;
    const slot = document.getElementById("passio-generic-content-slot");
    if (slot) slot.appendChild(preserved);
  };

  rebuildDashboardLayout();
  const historyRebuilt = rebuildHistoryLayout();
  if (!historyRebuilt) rebuildGenericPageLayout();
  wireDashboardActions().then(() => {
    const altStart = document.getElementById("start-btn-card");
    const mainStart = document.getElementById("start-btn");
    if (altStart && mainStart) {
      altStart.addEventListener("click", () => mainStart.click());
    }
  });

  document.querySelectorAll("header.nav, nav.nav, .cortie-global-nav").forEach((el) => {
    if (!el.classList.contains("n-nav")) el.style.display = "none";
  });

  let footer = document.querySelector("footer.rich-footer");
  if (!footer) {
    document.body.insertAdjacentHTML("beforeend", FOOTER_HTML);
  } else {
    footer.outerHTML = FOOTER_HTML;
  }

  const initMegaNav = () => {
    const links = document.getElementById("n-links");
    const mega = document.getElementById("n-mega");
    const title = document.getElementById("n-mega-title");
    const list = document.getElementById("n-mega-list");
    if (!links || !mega || !title || !list) return false;
    if (links.dataset.navReady === "1") return true;
    links.dataset.navReady = "1";

    let navGroups =
      Array.isArray(window.__CORTIE_NAV_GROUPS) && window.__CORTIE_NAV_GROUPS.length
        ? window.__CORTIE_NAV_GROUPS
        : DEFAULT_NAV_GROUPS;
    let active = "";
    const render = (label) => {
      const group = navGroups.find((entry) => entry.label === label);
      if (!group) {
        mega.style.display = "none";
        return;
      }
      title.textContent = group.label;
      list.innerHTML = group.items
        .map((item) => `<li><a class="n-mega-link" href="${item.href}"><strong>${item.name}</strong><span>${item.desc}</span></a></li>`)
        .join("");
      mega.style.display = "block";
    };
    const setActive = (label, buttons) => {
      active = label;
      buttons.forEach((btn) => btn.classList.toggle("active", btn.dataset.label === label));
      if (label) render(label);
      else mega.style.display = "none";
    };
    const mountGroups = (groups) => {
      navGroups = Array.isArray(groups) && groups.length ? groups : DEFAULT_NAV_GROUPS;
      links.innerHTML = navGroups.map((group) => `<li><button type="button" class="n-group-btn" data-label="${group.label}">${group.label}</button></li>`).join("");
      const buttons = [...links.querySelectorAll(".n-group-btn")];
      buttons.forEach((btn) => {
        btn.addEventListener("click", () => setActive(active === btn.dataset.label ? "" : btn.dataset.label, buttons));
        btn.addEventListener("mouseenter", () => setActive(btn.dataset.label, buttons));
      });
      if (active) render(active);
    };
    mountGroups(navGroups);
    mega.addEventListener("mouseleave", () => {
      const buttons = [...links.querySelectorAll(".n-group-btn")];
      setActive("", buttons);
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".n-nav") && !event.target.closest(".n-mega")) {
        const buttons = [...links.querySelectorAll(".n-group-btn")];
        setActive("", buttons);
      }
    });

    if (!Array.isArray(window.__CORTIE_NAV_GROUPS)) {
      const script = document.createElement("script");
      script.src = SHARED_NAV_CONFIG_JS;
      script.async = true;
      script.onload = () => {
        if (Array.isArray(window.__CORTIE_NAV_GROUPS) && window.__CORTIE_NAV_GROUPS.length) {
          mountGroups(window.__CORTIE_NAV_GROUPS);
        }
      };
      document.head.appendChild(script);
    }
    return true;
  };

  if (!initMegaNav()) {
    let retries = 20;
    const timer = setInterval(() => {
      retries -= 1;
      if (initMegaNav() || retries <= 0) clearInterval(timer);
    }, 150);
  }

  (async () => {
    const actions = document.getElementById("n-actions");
    if (!actions) return;
    try {
      const response = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (!response.ok) throw new Error("not logged in");
      const payload = await response.json();
      const userName = payload.user?.name || payload.user?.username || "Learner";
      actions.innerHTML = `<span class="n-user">${userName}</span><a class="n-login" id="global-logout-btn" href="${logoutUrl}">Logout</a><a class="n-start" href="/pages/dashboard.html">Study</a>`;
      document.getElementById("global-logout-btn")?.addEventListener("click", async () => {
        try {
          await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
        } catch (_err) {}
        location.href = logoutUrl;
      });
    } catch (_err) {
      actions.innerHTML = `<a href="${loginUrl}" class="n-login">Log in</a><a href="${signupUrl}" class="n-start">Get started</a>`;
    }
  })();
})();
