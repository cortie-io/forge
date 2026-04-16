const $ = id => document.getElementById(id);

const ST = {
  userName: "학습자",
  filters: [],
  certificate: "",
  subject: "",
  page: 1,
  pageSize: 20,
  total: 0,
  totalPages: 1,
  loading: false
};

function parseQuery() {
  const params = new URLSearchParams(location.search);
  const certificate = String(params.get("certificate") || "").trim();
  const subject = String(params.get("subject") || "").trim();
  const page = Math.max(1, Number(params.get("page") || 1) || 1);

  ST.certificate = certificate;
  ST.subject = subject;
  ST.page = page;
}

function syncQuery() {
  const params = new URLSearchParams();
  if (ST.certificate) {
    params.set("certificate", ST.certificate);
  }
  if (ST.subject) {
    params.set("subject", ST.subject);
  }
  params.set("page", String(ST.page));
  history.replaceState(null, "", `/pages/question-bank.html?${params.toString()}`);
}

function makeCard(question) {
  const article = document.createElement("article");
  article.className = "card bank-item";

  const preview = String(question.question || "").slice(0, 120);
  const shortPreview = String(question.question || "").length > 120 ? `${preview}...` : preview;
  const certLabel = String(question.certificate || "기타").trim();
  const subLabel = String(question.subSubject || question.subject || "세부 과목 없음").trim();

  article.innerHTML = `
    <div class='bank-item-head'>
      <strong>문제 ID ${question.id}</strong>
      <span class='dash-chip'>${certLabel} · ${subLabel}</span>
    </div>
    <div class='bank-q'>${shortPreview || "문항 내용 없음"}</div>
    <div class='bank-item-actions'>
      <a class='btn btn-navy btn-sm' href='/pages/quiz.html?questionId=${encodeURIComponent(String(question.id))}'>이 문제 풀기</a>
    </div>
  `;

  return article;
}

function setMetaText() {
  const from = ST.total === 0 ? 0 : (ST.page - 1) * ST.pageSize + 1;
  const to = Math.min(ST.page * ST.pageSize, ST.total);
  const certificateText = ST.certificate || "전체 자격증";
  const subjectText = ST.certificate
    ? (ST.subject ? ` · ${ST.subject}` : " · 전체 세부 과목")
    : " · 자격증을 선택하세요";
  $("bank-meta").textContent = `${certificateText}${subjectText} · ${from}-${to} / 총 ${ST.total}문제`;
  $("page-indicator").textContent = `${ST.page} / ${ST.totalPages}`;
}

function fillSubjectOptions() {
  const sel = $("subject-filter");
  const currentCertificate = ST.certificate;

  if (!currentCertificate) {
    ST.subject = "";
    sel.innerHTML = "";
    sel.disabled = true;
    return;
  }

  const cert = ST.filters.find(item => item.name === currentCertificate);
  const subjects = cert ? cert.subjects : [];

  const uniqueByValue = new Map();
  subjects.forEach(item => {
    if (!uniqueByValue.has(item.value)) {
      uniqueByValue.set(item.value, item);
    }
  });
  const uniqueSubjects = Array.from(uniqueByValue.values()).sort((a, b) => a.label.localeCompare(b.label, "ko"));

  sel.innerHTML = "<option value=''>전체 세부 과목</option>";
  uniqueSubjects.forEach(item => {
    const opt = document.createElement("option");
    opt.value = item.value;
    opt.textContent = `${item.label} (${item.count})`;
    sel.appendChild(opt);
  });

  sel.disabled = false;

  if (ST.subject && uniqueSubjects.some(item => item.value === ST.subject)) {
    sel.value = ST.subject;
  } else {
    ST.subject = "";
    sel.value = "";
  }
}

async function loadMe() {
  try {
    const r = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" });
    if (!r.ok) {
      location.href = "/pages/login.html";
      return false;
    }

    const d = await r.json();
    ST.userName = d.user?.name || d.user?.username || "학습자";
    $("user-name").textContent = ST.userName;
    $("ava-bank").textContent = ST.userName;
    $("ava-bank").title = ST.userName;
    return true;
  } catch (e) {
    location.href = "/pages/login.html";
    return false;
  }
}

async function loadSubjects() {
  const certSel = $("certificate-filter");
  const subSel = $("subject-filter");
  certSel.disabled = true;
  subSel.disabled = true;

  try {
    const r = await fetch("/api/question-bank/subjects", {
      credentials: "same-origin",
      cache: "no-store"
    });
    if (!r.ok) {
      throw new Error("필터 조회 실패");
    }

    const d = await r.json();
    const certificates = Array.isArray(d.certificates) ? d.certificates : [];
    ST.filters = certificates;

    certSel.innerHTML = "<option value=''>전체 자격증</option>";
    certificates.forEach(item => {
      const opt = document.createElement("option");
      opt.value = item.name;
      opt.textContent = `${item.name} (${item.count})`;
      certSel.appendChild(opt);
    });

    if (ST.certificate && certificates.some(item => item.name === ST.certificate)) {
      certSel.value = ST.certificate;
    } else {
      ST.certificate = "";
      certSel.value = "";
    }

    fillSubjectOptions();
  } catch (e) {
    certSel.innerHTML = "<option value=''>자격증을 불러오지 못했습니다</option>";
    subSel.innerHTML = "<option value=''>세부 과목을 불러오지 못했습니다</option>";
  } finally {
    certSel.disabled = false;
    subSel.disabled = !ST.certificate;
  }
}

async function loadQuestions() {
  if (ST.loading) {
    return;
  }

  ST.loading = true;
  const list = $("bank-list");
  const pagination = $("bank-pagination");
  list.innerHTML = "<section class='card panel'>문제를 불러오는 중...</section>";

  const params = new URLSearchParams();
  params.set("page", String(ST.page));
  params.set("pageSize", String(ST.pageSize));
  if (ST.certificate) {
    params.set("certificate", ST.certificate);
  }
  if (ST.subject) {
    params.set("subject", ST.subject);
  }

  try {
    const r = await fetch(`/api/question-bank/questions?${params.toString()}`, {
      credentials: "same-origin",
      cache: "no-store"
    });
    if (!r.ok) {
      throw new Error("문제 조회 실패");
    }

    const d = await r.json();
    const questions = Array.isArray(d.questions) ? d.questions : [];
    ST.total = Number(d.total) || 0;
    ST.page = Number(d.page) || 1;
    ST.pageSize = Number(d.pageSize) || 20;
    ST.totalPages = Math.max(1, Number(d.totalPages) || 1);

    if (!questions.length) {
      list.innerHTML = "<section class='card panel'>조건에 맞는 문제가 없습니다.</section>";
      pagination.style.display = "none";
      setMetaText();
      syncQuery();
      return;
    }

    list.innerHTML = "";
    questions.forEach(q => list.appendChild(makeCard(q)));

    pagination.style.display = "flex";
    $("btn-prev").disabled = ST.page <= 1;
    $("btn-next").disabled = ST.page >= ST.totalPages;

    setMetaText();
    syncQuery();
  } catch (e) {
    list.innerHTML = "<section class='card panel'>문제를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</section>";
    pagination.style.display = "none";
  } finally {
    ST.loading = false;
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

async function init() {
  parseQuery();

  const ok = await loadMe();
  if (!ok) {
    return;
  }

  $("btn-logout").onclick = doLogout;
  $("certificate-filter").onchange = e => {
    ST.certificate = String(e.target.value || "");
    ST.subject = "";
    ST.page = 1;
    fillSubjectOptions();
    loadQuestions();
  };

  $("subject-filter").onchange = e => {
    ST.subject = String(e.target.value || "");
    ST.page = 1;
    loadQuestions();
  };

  $("btn-prev").onclick = () => {
    if (ST.page <= 1) return;
    ST.page -= 1;
    loadQuestions();
  };

  $("btn-next").onclick = () => {
    if (ST.page >= ST.totalPages) return;
    ST.page += 1;
    loadQuestions();
  };

  await loadSubjects();
  await loadQuestions();
}

init();
