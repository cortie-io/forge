const $ = id => document.getElementById(id);
let pollTimer = null;

function readJobId() {
  const params = new URLSearchParams(location.search);
  const id = Number(params.get("jobId"));
  return Number.isInteger(id) && id > 0 ? id : null;
}

async function loadMe() {
  try {
    const r = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" });
    if (!r.ok) {
      location.href = "/pages/login.html";
      return false;
    }

    const d = await r.json();
    const full = d.user?.name || d.user?.username || "학습자";
    $("ava-loading").textContent = full;
    $("ava-loading").title = full;
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

function setStatus(text, type = "") {
  $("loading-status").textContent = text;
  const msg = $("loading-msg");
  msg.className = `msg ${type}`;
  msg.textContent = type === "err" ? text : "";
}

async function pollJob(jobId) {
  try {
    const r = await fetch(`/api/rag/jobs/${jobId}`, { credentials: "same-origin", cache: "no-store" });
    const d = await r.json();
    if (!r.ok) {
      setStatus(d.message || "작업 정보를 불러오지 못했습니다.", "err");
      return;
    }

    const job = d.job || {};
    if (job.status === "completed") {
      location.href = `/pages/history.html?ragJobId=${encodeURIComponent(String(jobId))}`;
      return;
    }

    if (job.status === "failed") {
      setStatus(job.errorMessage || "AI 해설 생성에 실패했습니다.", "err");
      return;
    }

    setStatus(job.status === "processing"
      ? "AI가 문제를 분석하고 해설을 작성하는 중입니다. 완료되면 히스토리로 이동합니다."
      : "작업 큐에 등록되었습니다. 곧 분석이 시작됩니다.");
  } catch (e) {
    setStatus("네트워크 오류로 상태를 확인하지 못했습니다.", "err");
  }
}

async function init() {
  const ok = await loadMe();
  if (!ok) return;

  $("btn-logout").onclick = doLogout;

  const jobId = readJobId();
  if (!jobId) {
    setStatus("유효한 작업 번호가 없습니다.", "err");
    return;
  }

  await pollJob(jobId);
  pollTimer = window.setInterval(() => {
    pollJob(jobId);
  }, 3000);
  window.addEventListener("beforeunload", () => {
    if (pollTimer) {
      window.clearInterval(pollTimer);
    }
  });
}

init();
