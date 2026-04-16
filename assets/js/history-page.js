const $ = id => document.getElementById(id);

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function readTargetRagJobId() {
  const params = new URLSearchParams(location.search);
  const id = Number(params.get("ragJobId"));
  return Number.isInteger(id) && id > 0 ? id : null;
}

function fmtDate(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function fmtDuration(sec) {
  const s = Math.max(0, Number(sec) || 0);
  const m = String(Math.floor(s / 60)).padStart(2, "0");
  const r = String(s % 60).padStart(2, "0");
  return `${m}:${r}`;
}

async function loadMe() {
  try {
    const r = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (!r.ok) {
      location.href = "/pages/login.html";
      return null;
    }

    const d = await r.json();
    const full = d.user?.name || d.user?.username || "학습자";
    $("user-name").textContent = full;
    $("ava-history").textContent = full;
    $("ava-history").title = full;
    return full;
  } catch (e) {
    location.href = "/pages/login.html";
    return null;
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

function renderAttemptCard(attempt) {
  const wrap = document.createElement("article");
  wrap.className = "card history-card";
  const quizIdLabel = attempt.quizUid ? `<span class='dash-chip'>Quiz ID ${attempt.quizUid}</span>` : "";
  wrap.innerHTML = `
    <div class='history-head'>
      <div>
        <strong class='history-title'>세션 #${attempt.id}</strong>
        <div class='muted'>${fmtDate(attempt.createdAt)}</div>
      </div>
      <div class='history-score'>${attempt.score}점</div>
    </div>
    <div class='history-meta'>
      ${quizIdLabel}
      <span class='dash-chip'>정답 ${attempt.correctCount}/${attempt.totalQuestions}</span>
      <span class='dash-chip'>소요 ${fmtDuration(attempt.durationSec)}</span>
    </div>
    <div class='history-actions'>
      <button class='btn btn-out btn-sm' data-action='toggle' data-id='${attempt.id}'>상세보기</button>
    </div>
    <div class='history-detail' id='attempt-detail-${attempt.id}' style='display:none;'></div>
  `;
  return wrap;
}

function renderRagJobCard(job) {
  const wrap = document.createElement("article");
  wrap.className = "card history-card rag-history-card";
  const statusLabel = job.status === "completed"
    ? "완료"
    : job.status === "failed"
      ? "실패"
      : job.status === "processing"
        ? "분석 중"
        : "대기 중";
  const badgeClass = job.status === "completed"
    ? "ok"
    : job.status === "failed"
      ? "ng"
      : "pending";
  wrap.innerHTML = `
    <div class='history-head'>
      <div>
        <strong class='history-title'>AI 해설 #${job.id}</strong>
        <div class='muted'>${fmtDate(job.createdAt)}</div>
      </div>
      <div class='status-pill ${badgeClass}'>${statusLabel}</div>
    </div>
    <div class='history-question-preview'>${escapeHtml(job.questionText || "문항 정보 없음")}</div>
    <div class='history-meta'>
      ${job.wrongChoice ? `<span class='dash-chip'>선택 오답 제공</span>` : `<span class='dash-chip'>오답 미제공</span>`}
      ${job.answerChoice ? `<span class='dash-chip'>정답 제공</span>` : `<span class='dash-chip'>정답 미제공</span>`}
    </div>
    <div class='history-actions'>
      <button class='btn btn-out btn-sm' data-action='toggle-rag' data-id='${job.id}'>상세보기</button>
    </div>
    <div class='history-detail' id='rag-detail-${job.id}' style='display:none;'></div>
  `;
  return wrap;
}

function renderAttemptDetail(container, attempt) {
  const answers = Array.isArray(attempt.answers) ? attempt.answers : [];
  if (!answers.length) {
    container.innerHTML = "<p class='muted'>상세 답안이 없습니다.</p>";
    return;
  }

  container.innerHTML = answers.map((a, idx) => `
    <div class='card answer-item ${a.isCorrect ? "ok" : "ng"}'>
      <div class='answer-subject'>${a.subject || "과목 정보 없음"}</div>
      <div class='answer-q'>${idx + 1}. ${a.questionText || "문항 정보 없음"}</div>
      <div class='tags'>
        <span class='tag ${a.isCorrect ? "ok" : "ng"}'>내 답: ${a.selectedIndex === null || a.selectedIndex === undefined ? "미선택" : a.selectedIndex + 1}</span>
        <span class='tag ok'>정답: ${Number(a.correctIndex) + 1}</span>
      </div>
    </div>
  `).join("");
}

function renderRagJobDetail(container, job) {
  if (!job) {
    container.innerHTML = "<p class='muted'>AI 해설 상세 정보를 찾을 수 없습니다.</p>";
    return;
  }

  if (job.status === "pending" || job.status === "processing") {
    container.innerHTML = "<section class='card panel'>AI가 아직 해설을 생성하는 중입니다. 잠시 후 다시 열어보세요.</section>";
    return;
  }

  if (job.status === "failed") {
    container.innerHTML = `<section class='card panel'>해설 생성에 실패했습니다. ${escapeHtml(job.errorMessage || "")}</section>`;
    return;
  }

  const responsePayload = job.resultPayload || {};
  const report = responsePayload.results?.[0]?.report || {};
  const body = report.body || {};
  const analysis = body.analysis || {};
  const correctionLabel = job.wrongChoice ? "오답 분석" : "함정 탈출 꿀팁!";
  const finalAnswer = job.answerChoice || body.answer || report.header?.ans || "정답 정보 없음";
  const options = [job.option1, job.option2, job.option3, job.option4].filter(Boolean);

  container.innerHTML = `
    <div class='rag-detail-grid'>
      <section class='card rag-detail-card'>
        <div class='rag-detail-label'>입력 문제</div>
        <div class='rag-detail-question'>${escapeHtml(job.questionText)}</div>
        <div class='rag-option-list'>
          ${options.map((opt, idx) => `<div class='rag-option-item'>${idx + 1}) ${escapeHtml(opt)}</div>`).join("")}
        </div>
        <div class='tags'>
          ${job.wrongChoice ? `<span class='tag ng'>내가 고른 오답: ${escapeHtml(job.wrongChoice)}</span>` : ""}
          <span class='tag ok'>정답: ${escapeHtml(finalAnswer)}</span>
        </div>
      </section>

      <section class='card rag-detail-card'>
        <div class='rag-detail-label'>AI 해설</div>
        <div class='rag-copy-block'>${escapeHtml(body.overview || "해설이 없습니다.")}</div>
      </section>

      <section class='card rag-detail-card'>
        <div class='rag-detail-label'>보기별 해설</div>
        <div class='rag-analysis-list'>
          ${Object.entries(analysis).map(([key, value]) => `
            <div class='rag-analysis-item'>
              <strong>${escapeHtml(key)}번 보기</strong>
              <p>${escapeHtml(value)}</p>
            </div>
          `).join("") || "<p class='muted'>보기별 해설이 없습니다.</p>"}
        </div>
      </section>

      <section class='card rag-detail-card'>
        <div class='rag-detail-label'>${correctionLabel}</div>
        <div class='rag-copy-block'>${escapeHtml(body.correction || "보충 설명이 없습니다.")}</div>
      </section>

      <section class='card rag-detail-card'>
        <div class='rag-detail-label'>Insight</div>
        <div class='rag-copy-block'>${escapeHtml(body.insight || "추가 인사이트가 없습니다.")}</div>
      </section>

      <section class='card rag-detail-card'>
        <div class='rag-detail-label'>시험장 한 줄 팁</div>
        <div class='rag-copy-block'>${escapeHtml(report.magic_tip || body.magic_tip || "추가 팁이 없습니다.")}</div>
      </section>
    </div>
  `;
}

async function loadQuizHistory() {
  const list = $("quiz-history-list");
  const empty = $("quiz-history-empty");

  try {
    const r = await fetch("/api/quiz/history?limit=300", { credentials: "same-origin" });
    if (!r.ok) {
      throw new Error("히스토리 조회 실패");
    }

    const d = await r.json();
    const attempts = Array.isArray(d.attempts) ? d.attempts : [];

    if (!attempts.length) {
      list.innerHTML = "";
      empty.style.display = "block";
      return;
    }

    empty.style.display = "none";
    list.innerHTML = "";
    attempts.forEach(attempt => {
      list.appendChild(renderAttemptCard(attempt));
    });

  } catch (e) {
    list.innerHTML = "<section class='card panel'>히스토리를 불러오지 못했습니다.</section>";
  }
}

async function loadRagHistory() {
  const list = $("rag-history-list");
  const empty = $("rag-history-empty");
  const targetJobId = readTargetRagJobId();

  try {
    const r = await fetch("/api/rag/history?limit=300", { credentials: "same-origin", cache: "no-store" });
    if (!r.ok) {
      throw new Error("AI 해설 히스토리 조회 실패");
    }

    const d = await r.json();
    const jobs = Array.isArray(d.jobs) ? d.jobs : [];

    if (!jobs.length) {
      list.innerHTML = "";
      empty.style.display = "block";
      return;
    }

    empty.style.display = "none";
    list.innerHTML = "";
    jobs.forEach(job => {
      list.appendChild(renderRagJobCard(job));
    });

    if (targetJobId) {
      const targetBtn = list.querySelector(`button[data-action='toggle-rag'][data-id='${targetJobId}']`);
      if (targetBtn) {
        targetBtn.click();
      }
    }
  } catch (e) {
    list.innerHTML = "<section class='card panel'>AI 해설 기록을 불러오지 못했습니다.</section>";
  }
}

async function handleQuizToggle(btn) {
  const attemptId = btn.getAttribute("data-id");
  const detail = $(`attempt-detail-${attemptId}`);
  if (!detail) return;

  if (detail.style.display === "none") {
    detail.style.display = "block";
    btn.textContent = "접기";

    if (!detail.dataset.loaded) {
      detail.innerHTML = "<p class='muted'>상세 기록을 불러오는 중...</p>";
      try {
        const rr = await fetch(`/api/quiz/history/${attemptId}`, { credentials: "same-origin" });
        if (!rr.ok) {
          throw new Error("상세 조회 실패");
        }
        const dd = await rr.json();
        renderAttemptDetail(detail, dd.attempt || {});
        detail.dataset.loaded = "1";
      } catch (err) {
        detail.innerHTML = "<p class='muted'>상세 기록을 불러오지 못했습니다.</p>";
      }
    }
  } else {
    detail.style.display = "none";
    btn.textContent = "상세보기";
  }
}

async function handleRagToggle(btn) {
  const jobId = btn.getAttribute("data-id");
  const detail = $(`rag-detail-${jobId}`);
  if (!detail) return;

  if (detail.style.display === "none") {
    detail.style.display = "block";
    btn.textContent = "접기";

    if (!detail.dataset.loaded) {
      detail.innerHTML = "<p class='muted'>AI 해설 상세 정보를 불러오는 중...</p>";
      try {
        const rr = await fetch(`/api/rag/jobs/${jobId}`, { credentials: "same-origin", cache: "no-store" });
        if (!rr.ok) {
          throw new Error("상세 조회 실패");
        }
        const dd = await rr.json();
        renderRagJobDetail(detail, dd.job || {});
        if ((dd.job || {}).status === "completed") {
          detail.dataset.loaded = "1";
        }
      } catch (err) {
        detail.innerHTML = "<p class='muted'>AI 해설 상세 정보를 불러오지 못했습니다.</p>";
      }
    }
  } else {
    detail.style.display = "none";
    btn.textContent = "상세보기";
  }
}

async function init() {
  const me = await loadMe();
  if (!me) return;

  $("btn-logout").onclick = doLogout;
  $("quiz-history-list").addEventListener("click", async e => {
    const btn = e.target.closest("button[data-action='toggle']");
    if (!btn) return;
    handleQuizToggle(btn);
  });

  $("rag-history-list").addEventListener("click", async e => {
    const btn = e.target.closest("button[data-action='toggle-rag']");
    if (!btn) return;
    handleRagToggle(btn);
  });

  await loadQuizHistory();
  await loadRagHistory();
}

init();
