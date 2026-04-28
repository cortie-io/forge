(() => {
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
        { name: "Auth Server", href: "https://auth.cortie.io/", desc: "Central SSO login and session authority." },
        { name: "Upload", href: "https://up.cortie.io", desc: "Fast file intake endpoint for service flows." },
        { name: "Storage", href: "https://storage.cortie.io", desc: "Shared storage browser for platform assets." }
      ]
    },
    {
      label: "Developers",
      items: [
        { name: "Docs", href: "https://cortie.io/docs", desc: "Integration guides and implementation docs." },
        { name: "API Center", href: "https://cortie.io/api", desc: "API modules, references, and examples." },
        { name: "Developer Console", href: "https://cortie.io/developers", desc: "Keys, admin tools, and release utilities." },
        { name: "n8n", href: "https://n8n.cortie.io", desc: "Workflow automation workspace and builders." },
        { name: "Changelog", href: "https://cortie.io/changelog", desc: "Recent platform and service updates." }
      ]
    },
    {
      label: "Company",
      items: [
        { name: "About", href: "https://cortie.io/about", desc: "Brand mission and execution narrative." },
        { name: "Status", href: "https://cortie.io/status", desc: "Live service health and uptime summary." },
        { name: "Contact", href: "https://cortie.io/contact", desc: "Partnership and project collaboration." },
        { name: "Careers", href: "https://cortie.io/careers", desc: "Open roles and team opportunities." }
      ]
    }
  ];
  const SHARED_NAV_CONFIG_JS = "https://cortie.io/assets/cortie-nav-config.js?v=20260425-navsync4";

  const tryInit = () => {
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
        .map(
          (item) =>
            `<li><a class="n-mega-link" href="${item.href}"><strong>${item.name}</strong><span>${item.desc}</span></a></li>`
        )
        .join("");
      mega.style.display = "block";
    };

    const setActive = (label, buttons) => {
      active = label;
      buttons.forEach((button) => button.classList.toggle("active", button.dataset.label === label));
      if (label) render(label);
      else mega.style.display = "none";
    };

    const mountGroups = (groups) => {
      navGroups = Array.isArray(groups) && groups.length ? groups : DEFAULT_NAV_GROUPS;
      links.innerHTML = navGroups.map(
        (group) => `<li><button type="button" class="n-group-btn" data-label="${group.label}">${group.label}</button></li>`
      ).join("");
      const buttons = [...links.querySelectorAll(".n-group-btn")];
      buttons.forEach((button) => {
        button.addEventListener("click", () => setActive(active === button.dataset.label ? "" : button.dataset.label, buttons));
        button.addEventListener("mouseenter", () => setActive(button.dataset.label, buttons));
      });
      if (active) render(active);
    };
    mountGroups(navGroups);

    mega.addEventListener("mouseleave", () => {
      const buttons = [...links.querySelectorAll(".n-group-btn")];
      setActive("", buttons);
    });
    document.querySelector(".n-nav")?.addEventListener("mouseleave", (event) => {
      if (!mega.contains(event.relatedTarget)) {
        const buttons = [...links.querySelectorAll(".n-group-btn")];
        setActive("", buttons);
      }
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

  if (!tryInit()) {
    let retries = 20;
    const timer = setInterval(() => {
      retries -= 1;
      if (tryInit() || retries <= 0) clearInterval(timer);
    }, 150);
  }
})();
