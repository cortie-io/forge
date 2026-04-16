const $ = id => document.getElementById(id);

async function loadMe() {
  try {
    const r = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" });
    if (!r.ok) {
      location.href = "/pages/login.html";
      return false;
    }

    const d = await r.json();
    const full = d.user?.name || d.user?.username || "학습자";
    $("user-name").textContent = full;
    $("ava-token").textContent = full;
    $("ava-token").title = full;
    return true;
  } catch (e) {
    location.href = "/pages/login.html";
    return false;
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

function fmtDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return "-";
  }
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function showMessage(type, text) {
  const msg = $("token-msg");
  msg.className = `msg ${type}`;
  msg.textContent = text;
}

async function revealToken() {
  const password = String($("confirm-password").value || "").trim();
  if (!password) {
    showMessage("err", "비밀번호를 입력해주세요.");
    return;
  }

  const revealBtn = $("btn-reveal");
  revealBtn.disabled = true;
  showMessage("", "토큰을 조회하는 중...");

  try {
    const r = await fetch("/api/auth/api-token/reveal", {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password })
    });

    const d = await r.json();

    if (!r.ok) {
      showMessage("err", d.message || "토큰을 조회하지 못했습니다.");
      return;
    }

    const token = String(d.token || "");
    $("token-value").value = token;
    $("btn-copy").disabled = !token;

    const expiresText = fmtDate(d.expiresAt);
    const rotatedText = d.rotatedAt ? ` · 갱신 시각 ${fmtDate(d.rotatedAt)}` : "";
    $("token-meta").textContent = `만료일 ${expiresText}${rotatedText}`;
    showMessage("ok", "토큰 조회 완료. 외부 API 호출에 사용할 수 있습니다.");
  } catch (e) {
    showMessage("err", "네트워크 오류로 토큰 조회에 실패했습니다.");
  } finally {
    revealBtn.disabled = false;
  }
}

async function copyToken() {
  const value = String($("token-value").value || "");
  if (!value) {
    return;
  }

  try {
    await navigator.clipboard.writeText(value);
    showMessage("ok", "토큰을 복사했습니다.");
  } catch (e) {
    showMessage("err", "복사에 실패했습니다. 브라우저 권한을 확인해주세요.");
  }
}

async function init() {
  const ok = await loadMe();
  if (!ok) {
    return;
  }

  $("btn-logout").onclick = doLogout;
  $("btn-reveal").onclick = revealToken;
  $("btn-copy").onclick = copyToken;
}

init();
