const $ = id => document.getElementById(id);

function showMessage(type, text) {
  const msg = $("explain-msg");
  msg.className = `msg ${type}`;
  msg.textContent = text;
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
    $("user-name").textContent = full;
    $("ava-explain").textContent = full;
    $("ava-explain").title = full;
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

function readOptions() {
  return [1, 2, 3, 4].map(n => String($(`opt-${n}`).value || "").trim());
}

async function submitSolve() {
  const question = String($("question-input").value || "").trim();
  const options = readOptions();
  const wrongChoice = String($("wrong-choice").value || "").trim();
  const answerChoice = String($("answer-choice").value || "").trim();

  if (!question) {
    showMessage("err", "문제를 입력해주세요.");
    return;
  }

  if (options.some(x => !x)) {
    showMessage("err", "보기 4개를 모두 입력해주세요.");
    return;
  }

  const btn = $("btn-solve");
  btn.disabled = true;
  showMessage("", "AI 해설 작업을 생성하는 중...");

  try {
    const r = await fetch("/api/rag/jobs", {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        question,
        options,
        wrongChoice,
        answerChoice,
        rebuild_db: false
      })
    });

    const d = await r.json();
    if (!r.ok) {
      showMessage("err", d.message || "AI 해설 요청 생성에 실패했습니다.");
      return;
    }

    location.href = `/pages/ai-loading.html?jobId=${encodeURIComponent(String(d.jobId))}`;
  } catch (e) {
    showMessage("err", "네트워크 오류로 요청을 생성하지 못했습니다.");
  } finally {
    btn.disabled = false;
  }
}

async function init() {
  const ok = await loadMe();
  if (!ok) return;

  $("btn-logout").onclick = doLogout;
  $("btn-solve").onclick = submitSolve;
}

init();
