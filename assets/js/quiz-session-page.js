const ST = {
  user: null,
  qs: [],
  ans: [],
  cur: 0,
  sel: null,
  startedAt: null,
  timerId: null,
  savedAttemptId: null,
  quizId: null,
  questionId: null
};
const $ = id => document.getElementById(id);

function createQuizId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }

  const t = Date.now().toString(36);
  const r = Math.random().toString(36).slice(2, 10);
  return `quiz-${t}-${r}`;
}

function readQuizIdFromUrl() {
  const params = new URLSearchParams(location.search);
  const id = String(params.get("quizId") || "").trim();
  return id || null;
}

function readQuestionIdFromUrl() {
  const params = new URLSearchParams(location.search);
  const value = Number(params.get("questionId"));
  if (!Number.isInteger(value) || value <= 0) {
    return null;
  }
  return value;
}

function setQuizParamsInUrl(quizId, questionId = null) {
  const params = new URLSearchParams();
  params.set("quizId", quizId);
  if (Number.isInteger(questionId) && questionId > 0) {
    params.set("questionId", String(questionId));
  }
  const next = `/pages/quiz.html?${params.toString()}`;
  window.history.replaceState(null, "", next);
}

function subjectIcon(subject) {
  if (subject.includes("TCP/IP")) return "🌐";
  if (subject.includes("네트워크 일반")) return "🧭";
  if (subject.includes("NOS")) return "🖥️";
  if (subject.includes("운용기기")) return "🛠️";
  return "📘";
}

function showResultScreen() {
  $("screen-quiz").style.display = "none";
  $("screen-result").style.display = "block";
  window.scrollTo(0, 0);
}

function setUserBadges(name) {
  const full = String(name || "학습자").trim();

  ["ava-quiz", "ava-result"].forEach(id => {
    const el = $(id);
    if (el) {
      el.textContent = full;
      el.title = full;
    }
  });
}

function setTimerText() {
  if (!ST.startedAt) return;
  const sec = Math.floor((Date.now() - ST.startedAt) / 1000);
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  $("quiz-time").textContent = `${m}:${s}`;
}

function bindHotkeys() {
  document.addEventListener("keydown", e => {
    if ($("screen-quiz").style.display !== "block") return;

    if (e.key === "Escape") {
      location.href = "/pages/dashboard.html";
      return;
    }

    if (e.key >= "1" && e.key <= "4") {
      const idx = Number(e.key) - 1;
      const btn = document.querySelector(`button[data-opt='${idx}']`);
      if (btn) btn.click();
    }

    if (e.key === "Enter" && !$("btn-next").disabled) {
      $("btn-next").click();
    }
  });
}

async function loadMe() {
  try {
    const r = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (!r.ok) {
      location.href = "/pages/login.html";
      return;
    }

    const d = await r.json();
    ST.user = d.user?.name || d.user?.username || "학습자";
    setUserBadges(ST.user);
  } catch (e) {
    location.href = "/pages/login.html";
  }
}

async function startQuiz() {
  ST.qs = [];
  ST.ans = [];
  ST.cur = 0;
  ST.sel = null;
  ST.startedAt = Date.now();
  ST.savedAttemptId = null;

  if (ST.timerId) clearInterval(ST.timerId);
  ST.timerId = setInterval(setTimerText, 1000);
  setTimerText();

  $("quiz-loading").style.display = "block";
  $("quiz-content").style.display = "none";

  try {
    const endpoint = ST.questionId
      ? `/api/quiz/questions?questionId=${encodeURIComponent(String(ST.questionId))}`
      : "/api/quiz/questions";
    const r = await fetch(endpoint, { credentials: "same-origin" });
    if (!r.ok) throw new Error("문제 호출 실패");

    const d = await r.json();
    ST.qs = d.questions || [];
    if (!ST.qs.length) throw new Error("문제가 없습니다");

    renderQuestion(0);
    $("quiz-loading").style.display = "none";
    $("quiz-content").style.display = "block";
  } catch (e) {
    $("quiz-loading").innerHTML = `<p style='color:var(--red)'>문제를 불러오지 못했습니다: ${e.message}</p>`;
  }
}

async function saveAttemptHistory(totalQuestions, correctCount, durationSec) {
  if (ST.savedAttemptId) {
    return;
  }

  const saveMsg = $("save-msg");
  if (saveMsg) {
    saveMsg.textContent = "기록 저장 중...";
  }

  const answers = ST.qs.map((q, i) => ({
    questionId: q.id,
    subject: q.subject,
    questionText: q.question,
    selectedIndex: ST.ans[i] ?? null,
    correctIndex: q.answer
  }));

  try {
    const r = await fetch("/api/quiz/attempts", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        quizId: ST.quizId,
        durationSec,
        answers
      })
    });

    if (!r.ok) {
      throw new Error("저장 실패");
    }

    const d = await r.json();
    ST.savedAttemptId = d.attemptId || true;

    if (saveMsg) {
      saveMsg.textContent = "기록이 저장되었습니다. 히스토리에서 확인할 수 있어요.";
    }
  } catch (e) {
    if (saveMsg) {
      saveMsg.textContent = "기록 저장에 실패했습니다. 다시 시도해주세요.";
    }
  }
}

function renderQuestion(i) {
  const q = ST.qs[i];
  const total = ST.qs.length;

  $("q-current").textContent = i + 1;
  $("q-total").textContent = total;
  $("q-no").textContent = `문제 ${i + 1} · ID ${q.id}`;
  $("q-subject").textContent = `${subjectIcon(q.subject)} 네트워크 관리사 2급 · ${q.subject}`;
  $("q-text").textContent = q.question;
  $("q-progress").style.width = `${((i + 1) / total) * 100}%`;

  const wrap = $("q-options");
  wrap.innerHTML = "";

  q.options.forEach((opt, idx) => {
    const b = document.createElement("button");
    b.className = "opt";
    b.dataset.opt = String(idx);
    b.innerHTML = `<span class='opt-tag'>${["A", "B", "C", "D"][idx]}</span>${opt}`;
    b.onclick = () => {
      wrap.querySelectorAll(".opt").forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      ST.sel = idx;
      $("btn-next").disabled = false;
    };
    wrap.appendChild(b);
  });

  ST.sel = null;
  $("btn-next").disabled = true;
  $("btn-next").textContent = i === total - 1 ? "결과 보기" : "다음 문제";
  $("remain-count").textContent = total - (i + 1);
}

function goNext() {
  ST.ans.push(ST.sel);

  if (ST.cur < ST.qs.length - 1) {
    ST.cur += 1;
    renderQuestion(ST.cur);
  } else {
    showResult();
  }
}

function showResult() {
  if (ST.timerId) clearInterval(ST.timerId);
  showResultScreen();

  const total = ST.qs.length;
  let ok = 0;
  ST.qs.forEach((q, i) => {
    if (ST.ans[i] === q.answer) ok += 1;
  });
  const score = Math.round((ok / total) * 100);

  $("score").textContent = `${score}점`;
  $("score-msg").textContent =
    score >= 80
      ? "훌륭합니다! 합격권입니다."
      : score >= 60
        ? "좋아요! 오답 복습하면 더 올라갑니다."
        : "기초부터 다시 점검해봐요.";

  $("score-ok").textContent = `정답 ${ok}개`;
  $("score-ng").textContent = `오답 ${total - ok}개`;

  const spent = Math.floor((Date.now() - ST.startedAt) / 1000);
  const m = String(Math.floor(spent / 60)).padStart(2, "0");
  const s = String(spent % 60).padStart(2, "0");
  $("spent-time").textContent = `${m}:${s}`;

  saveAttemptHistory(total, ok, spent);

  const list = $("result-list");
  list.innerHTML = "";

  ST.qs.forEach((q, i) => {
    const isOk = ST.ans[i] === q.answer;
    const my = q.options[ST.ans[i]] || "미선택";
    const correct = q.options[q.answer];
    const el = document.createElement("div");
    el.className = `card answer-item ${isOk ? "ok" : "ng"}`;
    el.innerHTML = `
      <div class='answer-subject'>${subjectIcon(q.subject)} ${q.subject}</div>
      <div class='answer-q'>${i + 1}. ${q.question}</div>
      <div class='tags'>
        <span class='tag ${isOk ? "ok" : "ng"}'>내 답: ${my}</span>
        ${isOk ? "" : `<span class='tag ok'>정답: ${correct}</span>`}
      </div>
    `;
    list.appendChild(el);
  });
}

function init() {
  const questionId = readQuestionIdFromUrl();
  const quizId = questionId ? null : (readQuizIdFromUrl() || createQuizId());

  ST.quizId = quizId;
  ST.questionId = questionId;

  if (quizId) {
    sessionStorage.setItem("activeQuizId", quizId);
    setQuizParamsInUrl(quizId, null);
  } else {
    const params = new URLSearchParams();
    params.set("questionId", String(questionId));
    history.replaceState(null, "", `/pages/quiz.html?${params.toString()}`);
  }

  bindHotkeys();
  loadMe();
  startQuiz();

  $("btn-next").onclick = goNext;
  $("btn-exit").onclick = () => {
    location.href = "/pages/dashboard.html";
  };
  $("btn-retry").onclick = () => {
    if (ST.questionId) {
      $("screen-result").style.display = "none";
      $("screen-quiz").style.display = "block";
      startQuiz();
      return;
    }
    const nextQuizId = createQuizId();
    ST.quizId = nextQuizId;
    sessionStorage.setItem("activeQuizId", nextQuizId);
    setQuizParamsInUrl(nextQuizId, null);
    $("screen-result").style.display = "none";
    $("screen-quiz").style.display = "block";
    startQuiz();
  };
  $("btn-home").onclick = () => {
    location.href = "/pages/index.html";
  };
}

init();
