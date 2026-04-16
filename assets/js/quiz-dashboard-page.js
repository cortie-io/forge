const $ = id => document.getElementById(id);

function createQuizId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }

  const t = Date.now().toString(36);
  const r = Math.random().toString(36).slice(2, 10);
  return `quiz-${t}-${r}`;
}

function setDashboardUserName(name) {
  const full = String(name || "학습자").trim();
  const userName = $("user-name");
  const avatar = $("ava-dash");

  if (userName) {
    userName.textContent = full;
  }

  if (avatar) {
    avatar.textContent = full;
    avatar.title = full;
  }
}

async function loadMe() {
  try {
    const r = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (!r.ok) {
      location.href = "/pages/login.html";
      return;
    }

    const d = await r.json();
    const full = d.user?.name || d.user?.username || "학습자";
    setDashboardUserName(full);
  } catch (e) {
    location.href = "/pages/login.html";
  }
}

async function doLogout() {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  } catch (e) {
    // Ignore network errors.
  }

  location.href = "/pages/index.html";
}

function init() {
  loadMe();

  const startBtn = $("start-btn");
  const logoutBtn = $("btn-logout");

  if (startBtn) {
    startBtn.onclick = () => {
      sessionStorage.setItem("selectedSubject", "network-admin-2");
      const quizId = createQuizId();
      sessionStorage.setItem("activeQuizId", quizId);
      location.href = `/pages/quiz.html?quizId=${encodeURIComponent(quizId)}`;
    };
  }

  if (logoutBtn) {
    logoutBtn.onclick = doLogout;
  }
}

init();
