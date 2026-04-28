/**
 * Passio / Sikdorak — Express API (passio-node)
 *
 * 역할 요약
 * - 사용자 인증(JWT access + refresh cookie), 퀴즈/히스토리/문제은행 API
 * - AI 해설 “작업 큐”(`/api/rag2/jobs`): DB에 job을 만들고 백그라운드에서 Python RAG를 호출
 * - 퀴즈 세션 PDF(`/api/quiz/history/:id/pdf`)
 *
 * 배치/런타임
 * - 기본 listen: 127.0.0.1:3100 (Nginx가 `/api/*` 대부분을 여기로 프록시)
 * - Python RAG: `RAG_API_URL`(기본 http://127.0.0.1:8001)로 프록시 호출
 *
 * Nginx 라우팅 주의
 * - `/api/rag2/*`는 반드시 Node로 가야 함(주석: nginx 설정에서 `/api/rag/*`보다 위)
 *
 * 상세 아키텍처 문서: `docs/SYSTEM-ARCHITECTURE.md`
 */
// /api/rag2/jobs: Nginx에서 Node.js로 직접 프록시되는 경로 (linkage 저장용)
const express = require("express");
const helmet = require("helmet");
const cors = require("cors");
const compression = require("compression");
const morgan = require("morgan");
const rateLimit = require("express-rate-limit");
const crypto = require("node:crypto");
const path = require("node:path");
const cookieParser = require("cookie-parser");
const jwt = require("jsonwebtoken");
const {
  initDatabase,
  createUser,
  verifyUser,
  verifyUserPasswordById,
  findUserByEmail,
  findUserByUsername,
  findUserById,
  issueOrGetApiTokenByUserId,
  findUserByApiToken,
  storeRefreshToken,
  findRefreshToken,
  revokeRefreshToken,
  revokeAllRefreshTokensByUser,
  purgeExpiredRefreshTokens,
  getQuizQuestions,
  getQuestionById,
  getQuestionBankFilters,
  getQuestionBank,
  saveQuizAttempt,
  getQuizHistoryByUser,
  getQuizAttemptDetail,
  createRagSolveJob,
  getRagSolveJobById,
  markRagSolveJobProcessing,
  completeRagSolveJob,
  failRagSolveJob,
  getRagSolveHistoryByUser,
  getRagSolveJobDetail
} = require("./db");
const { buildQuizAttemptPdfBuffer, computePdfReadiness } = require("./attemptPdf");

const app = express();
const PORT = Number(process.env.PORT || 3100);
const ALLOWED_ORIGIN = process.env.ALLOWED_ORIGIN || "*";
const WEB_ROOT = path.resolve(__dirname, "..");
const AUTH_SERVER_INTROSPECT_URL =
  process.env.AUTH_SERVER_INTROSPECT_URL || "https://auth.cortie.io/api/auth/introspect";
const AUTH_SERVER_LOGIN_URL =
  process.env.AUTH_SERVER_LOGIN_URL || "https://auth.cortie.io/login";
const AUTH_SERVER_SIGNUP_URL =
  process.env.AUTH_SERVER_SIGNUP_URL || "https://auth.cortie.io/signup";
const AUTH_COOKIE_NAME = process.env.AUTH_COOKIE_NAME || "cortie_auth_token";
const JWT_ACCESS_SECRET = process.env.JWT_ACCESS_SECRET || "dev_access_secret_change_me";
const JWT_REFRESH_SECRET = process.env.JWT_REFRESH_SECRET || "dev_refresh_secret_change_me";
const ACCESS_TOKEN_EXPIRES = process.env.ACCESS_TOKEN_EXPIRES || "15m";
const REFRESH_TOKEN_EXPIRES_DAYS = Number(process.env.REFRESH_TOKEN_EXPIRES_DAYS || 14);
const IS_PROD = process.env.NODE_ENV === "production";
const THEMAZE_SOURCE_URL = process.env.THEMAZE_SOURCE_URL || "http://themazenw.co.kr/adm/";
const THEMAZE_SOURCE_COOKIE = process.env.THEMAZE_SOURCE_COOKIE || "";
const THEMAZE_LOGIN_URL = process.env.THEMAZE_LOGIN_URL || "http://themazenw.co.kr/bbs/login.php?url=http%3A%2F%2Fthemazenw.co.kr%2Fadm";
const THEMAZE_LOGIN_CHECK_URL =
  process.env.THEMAZE_LOGIN_CHECK_URL || "http://themazenw.co.kr/bbs/login_check.php";
const THEMAZE_ADMIN_ID = process.env.THEMAZE_ADMIN_ID || "admin";
const THEMAZE_ADMIN_PASSWORD = process.env.THEMAZE_ADMIN_PASSWORD || "angel1004";

app.set("trust proxy", 1);

app.use((req, res, next) => {
  const requestId = req.header("x-request-id") || crypto.randomUUID();
  req.requestId = requestId;
  res.setHeader("x-request-id", requestId);
  next();
});

app.use(morgan(":date[iso] :method :url :status :response-time ms req_id=:req[x-request-id]"));
app.use(compression());
app.use(express.json({ limit: "1mb" }));
app.use(cookieParser());

app.use(
  helmet({
    crossOriginResourcePolicy: { policy: "cross-origin" }
  })
);

app.use(
  cors({
    origin: ALLOWED_ORIGIN === "*" ? true : ALLOWED_ORIGIN.split(","),
    credentials: true
  })
);

const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 120,
  standardHeaders: true,
  legacyHeaders: false
});

app.use("/api", apiLimiter);

const authLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 20,
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    error: "too_many_requests",
    message: "잠시 후 다시 시도해주세요."
  }
});

app.use("/api/auth", authLimiter);

/** AI 해설 job 생성 — 전 서버 합산 (다수 사용자 동시 폭주 방지) */
const rag2JobGlobalLimiter = rateLimit({
  windowMs: 60_000,
  limit: Math.max(20, Number(process.env.RAG2_JOBS_GLOBAL_PER_MIN || 150)),
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: () => "__rag2_jobs_global__",
  message: {
    error: "rag_server_busy",
    message: "지금 해설 요청이 많습니다. 잠시 후 다시 시도해 주세요."
  }
});

/** 계정당 분당 job 생성 상한 */
const rag2JobUserLimiter = rateLimit({
  windowMs: 60_000,
  limit: Math.max(8, Number(process.env.RAG2_JOBS_PER_USER_PER_MIN || 40)),
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator(req) {
    return req.user && req.user.id != null ? `rag2:uid:${req.user.id}` : `rag2:ip:${req.ip}`;
  },
  message: {
    error: "too_many_rag_jobs",
    message: "같은 계정에서 AI 해설 요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."
  }
});

/** 동기 RAG 일괄 solve — 사용자·토큰별 */
const ragSolveDirectUserLimiter = rateLimit({
  windowMs: 60_000,
  limit: Math.max(5, Number(process.env.RAG_SOLVE_DIRECT_PER_USER_PER_MIN || 20)),
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator(req) {
    if (req.user && req.user.id != null) {
      return `rag_solve:uid:${req.user.id}`;
    }
    return `rag_solve:ip:${req.ip}`;
  },
  message: {
    error: "too_many_rag_solve",
    message: "RAG 일괄 요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."
  }
});

const ragSolveDirectGlobalLimiter = rateLimit({
  windowMs: 60_000,
  limit: Math.max(10, Number(process.env.RAG_SOLVE_DIRECT_GLOBAL_PER_MIN || 60)),
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: () => "__rag_solve_direct_global__",
  message: {
    error: "rag_server_busy",
    message: "서버에 RAG 요청이 몰렸습니다. 잠시 후 다시 시도해 주세요."
  }
});

const QUIZ_SESSION_BUNDLE = path.join(WEB_ROOT, "assets", "js", "quiz-session.js");
app.get("/assets/js/quiz-session-page.js", (_req, res) => {
  res.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0");
  res.set("Pragma", "no-cache");
  res.set("Expires", "0");
  res.sendFile(QUIZ_SESSION_BUNDLE);
});

app.use(
  "/assets",
  express.static(path.join(WEB_ROOT, "assets"), {
    setHeaders(res, filePath) {
      if (/\.(?:js|mjs|css)$/i.test(filePath)) {
        res.setHeader(
          "Cache-Control",
          "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
        );
        res.setHeader("Pragma", "no-cache");
        res.setHeader("Expires", "0");
      }
    },
  })
);
app.use(
  "/pages",
  express.static(path.join(WEB_ROOT, "pages"), {
    setHeaders(res, filePath) {
      if (/\.html$/i.test(filePath)) {
        res.setHeader(
          "Cache-Control",
          "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
        );
        res.setHeader("Pragma", "no-cache");
        res.setHeader("Expires", "0");
      }
    }
  })
);

app.get("/", (req, res) => {
  res.redirect("/pages/index.html");
});

const pageAliases = {
  "/index.html": "/pages/index.html",
  "/login.html": "/pages/login.html",
  "/signup.html": "/pages/signup.html",
  "/dashboard.html": "/pages/dashboard.html",
  "/history.html": "/pages/history.html",
  "/admin": "/pages/admin.html",
  "/admin.html": "/pages/admin.html",
  "/themaze.html": "/pages/themaze.html"
};

Object.entries(pageAliases).forEach(([routePath, targetPath]) => {
  app.get(routePath, (req, res) => {
    res.redirect(targetPath);
  });
});

function decodeHtmlEntities(input) {
  return String(input || "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/g, "'");
}

function plainTextFromCellHtml(cellHtml) {
  return decodeHtmlEntities(String(cellHtml || "").replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, ""))
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function parseTableToMatrix(tableHtml) {
  const trMatches = tableHtml.match(/<tr[\s\S]*?<\/tr>/gi) || [];
  const matrix = [];
  const occupied = {};
  let maxCols = 0;

  const occupy = (r, c, rs, cs, value) => {
    for (let rr = r; rr < r + rs; rr += 1) {
      for (let cc = c; cc < c + cs; cc += 1) {
        occupied[`${rr}:${cc}`] = value;
      }
    }
  };

  trMatches.forEach((trHtml, rowIdx) => {
    const cellMatches = trHtml.match(/<(td|th)\b[\s\S]*?<\/\1>/gi) || [];
    let colIdx = 0;
    if (!matrix[rowIdx]) matrix[rowIdx] = [];

    cellMatches.forEach((cellHtml) => {
      while (occupied[`${rowIdx}:${colIdx}`]) {
        colIdx += 1;
      }
      const rowspanMatch = cellHtml.match(/\browspan\s*=\s*["']?(\d+)["']?/i);
      const colspanMatch = cellHtml.match(/\bcolspan\s*=\s*["']?(\d+)["']?/i);
      const rowspan = Math.max(1, Number(rowspanMatch?.[1] || 1));
      const colspan = Math.max(1, Number(colspanMatch?.[1] || 1));
      const inner = cellHtml.replace(/^<[^>]+>/, "").replace(/<\/(td|th)>$/i, "");
      const text = plainTextFromCellHtml(inner);

      occupy(rowIdx, colIdx, rowspan, colspan, text);
      matrix[rowIdx][colIdx] = text;
      colIdx += colspan;
      maxCols = Math.max(maxCols, colIdx);
    });
  });

  const normalized = [];
  for (let r = 0; r < matrix.length; r += 1) {
    const row = [];
    for (let c = 0; c < maxCols; c += 1) {
      row.push(occupied[`${r}:${c}`] || "");
    }
    normalized.push(row);
  }
  return normalized;
}

function extractBestTable(html) {
  const tableMatches = html.match(/<table\b[\s\S]*?<\/table>/gi) || [];
  if (!tableMatches.length) return null;
  let best = null;
  let bestScore = -1;
  tableMatches.forEach((tableHtml) => {
    const rows = (tableHtml.match(/<tr\b/gi) || []).length;
    const cells = (tableHtml.match(/<(td|th)\b/gi) || []).length;
    const score = rows * 10 + cells;
    if (score > bestScore) {
      best = tableHtml;
      bestScore = score;
    }
  });
  return best;
}

function updateCookieJarFromResponse(cookieJar, response) {
  const getter = response.headers.getSetCookie;
  const rawCookies =
    typeof getter === "function" ? getter.call(response.headers) : response.headers.get("set-cookie") ? [response.headers.get("set-cookie")] : [];
  rawCookies.forEach((entry) => {
    const pair = String(entry || "").split(";")[0].trim();
    if (!pair || !pair.includes("=")) return;
    const [name] = pair.split("=");
    if (!name) return;
    cookieJar[name.trim()] = pair;
  });
}

function buildCookieHeader(cookieJar) {
  return Object.values(cookieJar).join("; ");
}

async function fetchThemazeHtmlWithLogin(sourceUrl) {
  const cookieJar = {};

  if (THEMAZE_SOURCE_COOKIE) {
    THEMAZE_SOURCE_COOKIE.split(";").forEach((chunk) => {
      const pair = chunk.trim();
      if (!pair || !pair.includes("=")) return;
      const [name] = pair.split("=");
      cookieJar[name.trim()] = pair;
    });
  }

  const commonHeaders = {
    "user-agent": "Mozilla/5.0 (compatible; CortieThemazeBot/1.0)"
  };

  const firstRes = await fetch(sourceUrl, {
    method: "GET",
    headers: {
      ...commonHeaders,
      ...(buildCookieHeader(cookieJar) ? { cookie: buildCookieHeader(cookieJar) } : {})
    },
    redirect: "follow",
    signal: AbortSignal.timeout(12000)
  });
  updateCookieJarFromResponse(cookieJar, firstRes);
  let html = await firstRes.text();

  const authRequired =
    html.includes("로그인 하십시오") ||
    html.includes("오류안내 페이지") ||
    /\/bbs\/login\.php/i.test(html);
  if (!authRequired) {
    return { html, cookieJar, loggedIn: Boolean(THEMAZE_SOURCE_COOKIE) };
  }

  const loginPage = await fetch(THEMAZE_LOGIN_URL, {
    method: "GET",
    headers: {
      ...commonHeaders,
      ...(buildCookieHeader(cookieJar) ? { cookie: buildCookieHeader(cookieJar) } : {})
    },
    redirect: "follow",
    signal: AbortSignal.timeout(12000)
  });
  updateCookieJarFromResponse(cookieJar, loginPage);
  const loginHtml = await loginPage.text();
  const urlValue =
    loginHtml.match(/name=["']url["']\s+value=['"]([^'"]+)['"]/i)?.[1] || encodeURIComponent("http://themazenw.co.kr/adm");

  const form = new URLSearchParams();
  form.set("mb_id", THEMAZE_ADMIN_ID);
  form.set("mb_password", THEMAZE_ADMIN_PASSWORD);
  form.set("url", urlValue);

  const loginCheck = await fetch(THEMAZE_LOGIN_CHECK_URL, {
    method: "POST",
    headers: {
      ...commonHeaders,
      "content-type": "application/x-www-form-urlencoded",
      ...(buildCookieHeader(cookieJar) ? { cookie: buildCookieHeader(cookieJar) } : {})
    },
    body: form.toString(),
    redirect: "follow",
    signal: AbortSignal.timeout(12000)
  });
  updateCookieJarFromResponse(cookieJar, loginCheck);
  await loginCheck.text();

  const secondRes = await fetch(sourceUrl, {
    method: "GET",
    headers: {
      ...commonHeaders,
      ...(buildCookieHeader(cookieJar) ? { cookie: buildCookieHeader(cookieJar) } : {})
    },
    redirect: "follow",
    signal: AbortSignal.timeout(12000)
  });
  updateCookieJarFromResponse(cookieJar, secondRes);
  html = await secondRes.text();
  return { html, cookieJar, loggedIn: true };
}

app.get("/api/themaze/timetable", asyncHandler(async (req, res) => {
  const sourceUrl = String(req.query.url || THEMAZE_SOURCE_URL).trim();
  const { html, loggedIn } = await fetchThemazeHtmlWithLogin(sourceUrl);
  const title = (html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] || "").trim();
  const authRequired =
    html.includes("로그인 하십시오") ||
    html.includes("오류안내 페이지") ||
    /\/bbs\/login\.php/i.test(html);

  if (authRequired) {
    return res.status(401).json({
      ok: false,
      authRequired: true,
      sourceUrl,
      message: "Source page requires login. Check THEMAZE admin credentials/cookie.",
      title
    });
  }

  const tableHtml = extractBestTable(html);
  if (!tableHtml) {
    return res.status(422).json({
      ok: false,
      sourceUrl,
      message: "No table found in source HTML.",
      title
    });
  }

  const rows = parseTableToMatrix(tableHtml);
  return res.json({
    ok: true,
    sourceUrl,
    loggedIn,
    title,
    fetchedAt: new Date().toISOString(),
    rowCount: rows.length,
    colCount: rows[0]?.length || 0,
    rows
  });
}));

function normalizeUsername(username) {
  return String(username).trim().toLowerCase();
}

function getRefreshExpiryDate() {
  return new Date(Date.now() + REFRESH_TOKEN_EXPIRES_DAYS * 24 * 60 * 60 * 1000);
}

function createAccessToken(user) {
  return jwt.sign(
    {
      sub: String(user.id),
      username: user.username,
      email: user.email,
      name: user.name,
      studentNumber: user.studentNumber,
      type: "access"
    },
    JWT_ACCESS_SECRET,
    { expiresIn: ACCESS_TOKEN_EXPIRES }
  );
}

function createRefreshToken(user) {
  const jti = crypto.randomUUID();
  const token = jwt.sign(
    {
      sub: String(user.id),
      jti,
      type: "refresh"
    },
    JWT_REFRESH_SECRET,
    { expiresIn: `${REFRESH_TOKEN_EXPIRES_DAYS}d` }
  );

  return { token, jti };
}

function setAuthCookies(res, accessToken, refreshToken) {
  res.cookie("access_token", accessToken, {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: "lax",
    maxAge: 15 * 60 * 1000,
    path: "/"
  });

  res.cookie("refresh_token", refreshToken, {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: "lax",
    maxAge: REFRESH_TOKEN_EXPIRES_DAYS * 24 * 60 * 60 * 1000,
    path: "/api/auth"
  });
}

function clearAuthCookies(res) {
  res.clearCookie("access_token", { path: "/" });
  res.clearCookie("refresh_token", { path: "/api/auth" });
}

function getAccessTokenFromRequest(req) {
  const ssoCookie = req.cookies?.[AUTH_COOKIE_NAME];
  if (ssoCookie) {
    return ssoCookie;
  }

  const fromCookie = req.cookies?.access_token;
  if (fromCookie) {
    return fromCookie;
  }

  const authHeader = req.header("authorization") || "";
  const [scheme, token] = authHeader.split(" ");
  if (scheme?.toLowerCase() === "bearer" && token) {
    return token;
  }

  return null;
}

function normalizeAuthUsername(rawUsername, rawEmail) {
  const source = String(rawUsername || "").trim() || String(rawEmail || "").split("@")[0] || "user";
  const normalized = source.toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 30);
  if (!normalized) return `user_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  if (normalized.length < 3) return `${normalized}_u`;
  return normalized;
}

function makeStudentNumber(payloadSub) {
  const base = String(payloadSub || "").replace(/[^a-zA-Z0-9]/g, "").slice(0, 20);
  if (!base) return `auth${Date.now().toString().slice(-10)}`;
  const candidate = `auth${base}`;
  return candidate.length >= 4 ? candidate.slice(0, 30) : `auth_${base}`.slice(0, 30);
}

async function introspectAuthToken(token) {
  try {
    const resp = await fetch(AUTH_SERVER_INTROSPECT_URL, {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`
      },
      signal: AbortSignal.timeout(5000)
    });
    if (!resp.ok) {
      return null;
    }
    const body = await resp.json();
    if (!body?.active || !body?.payload) {
      return null;
    }
    return body.payload;
  } catch (_err) {
    return null;
  }
}

async function resolveOrCreateLocalUserFromAuthPayload(payload) {
  const authEmail = String(payload?.email || "").trim().toLowerCase();
  const username = normalizeAuthUsername(payload?.username, authEmail);
  const name = String(payload?.name || username).trim() || username;

  let localUser = null;
  if (authEmail) {
    localUser = await findUserByEmail(authEmail);
  }
  if (!localUser && username) {
    localUser = await findUserByUsername(username);
  }
  if (localUser) {
    return localUser;
  }

  const fallbackEmail = authEmail || `${username}@cortie.io`;
  const fallbackStudentNumber = makeStudentNumber(payload?.sub);
  const randomPassword = crypto.randomUUID() + crypto.randomUUID();

  try {
    const created = await createUser({
      username,
      email: fallbackEmail,
      name,
      password: randomPassword,
      studentNumber: fallbackStudentNumber
    });
    return created;
  } catch (_err) {
    // Race-safe fallback: user may have been created between lookups.
    return (await findUserByEmail(fallbackEmail)) || (await findUserByUsername(username));
  }
}

function getApiTokenFromRequest(req) {
  const fromHeader = String(req.header("x-api-token") || "").trim();
  if (fromHeader) {
    return fromHeader;
  }

  const authHeader = String(req.header("authorization") || "").trim();
  if (!authHeader) {
    return null;
  }

  const [scheme, token] = authHeader.split(" ");
  if (!scheme || !token) {
    return null;
  }

  const normalizedScheme = scheme.toLowerCase();
  if (normalizedScheme === "apikey") {
    return token;
  }

  // Bearer 토큰 중 API 키(prefix psk_)도 허용해 외부 호출 UX를 단순화한다.
  if (normalizedScheme === "bearer" && token.startsWith("psk_")) {
    return token;
  }

  return null;
}

function asyncHandler(handler) {
  return (req, res, next) => {
    Promise.resolve(handler(req, res, next)).catch(next);
  };
}

function makeRagOptionString(options) {
  return options.map((opt, idx) => `${idx + 1}) ${opt}`).join(", ");
}

function formatRagChoice(choiceText, options) {
  const raw = String(choiceText || "").trim();
  if (!raw) {
    return "-";
  }

  const prefixed = raw.match(/^([1-4])\)\s*(.+)$/);
  if (prefixed) {
    const idx = Number(prefixed[1]) - 1;
    if (idx >= 0 && idx < options.length) {
      return `${idx + 1}) ${options[idx]}`;
    }
    return `${prefixed[1]}) ${prefixed[2].trim()}`;
  }

  const normalized = raw.toLowerCase();
  const foundIndex = options.findIndex(opt => String(opt || "").trim().toLowerCase() === normalized);
  if (foundIndex >= 0) {
    return `${foundIndex + 1}) ${options[foundIndex]}`;
  }

  return raw;
}

function normalizeRagSolveInput(body) {
  const question = String(body?.question || body?.q || "").trim();
  const options = Array.isArray(body?.options)
    ? body.options.map(x => String(x || "").trim()).filter(Boolean)
    : [];
  const wrongChoice = String(body?.wrongChoice || body?.wrong || "").trim();
  const answerChoice = String(body?.answerChoice || body?.ans || "").trim();
  const rebuildDb = Boolean(body?.rebuild_db);

  return { question, options, wrongChoice, answerChoice, rebuildDb };
}

const requireAuth = asyncHandler(async (req, res, next) => {
  const accessToken = getAccessTokenFromRequest(req);
  if (!accessToken) {
    return res.status(401).json({
      error: "unauthorized",
      message: "로그인이 필요합니다."
    });
  }

  // Prefer global auth-server token so every cortie service shares one login.
  const authPayload = await introspectAuthToken(accessToken);
  if (authPayload) {
    const localUser = await resolveOrCreateLocalUserFromAuthPayload(authPayload);
    if (!localUser) {
      return res.status(401).json({
        error: "user_not_found",
        message: "사용자를 찾을 수 없습니다."
      });
    }
    req.user = localUser;
    req.authType = "global_session";
    req.authPayload = authPayload;
    return next();
  }

  // Backward-compat: accept legacy local JWT cookies/tokens.
  let payload;
  try {
    payload = jwt.verify(accessToken, JWT_ACCESS_SECRET);
  } catch (error) {
    return res.status(401).json({
      error: "invalid_token",
      message: "유효하지 않은 인증 토큰입니다."
    });
  }

  const user = await findUserById(payload.sub);
  if (!user) {
    return res.status(401).json({
      error: "user_not_found",
      message: "사용자를 찾을 수 없습니다."
    });
  }

  req.user = user;
  next();
});

const requireAuthOrApiToken = asyncHandler(async (req, res, next) => {
  const accessToken = getAccessTokenFromRequest(req);
  if (accessToken) {
    const authPayload = await introspectAuthToken(accessToken);
    if (authPayload) {
      const localUser = await resolveOrCreateLocalUserFromAuthPayload(authPayload);
      if (localUser) {
        req.user = localUser;
        req.authType = "global_session";
        req.authPayload = authPayload;
        return next();
      }
    }

    try {
      const payload = jwt.verify(accessToken, JWT_ACCESS_SECRET);
      const user = await findUserById(payload.sub);
      if (user) {
        req.user = user;
        req.authType = "session";
        return next();
      }
    } catch (error) {
      // 세션 토큰이 잘못되면 API 토큰 검증으로 폴백한다.
    }
  }

  const apiToken = getApiTokenFromRequest(req);
  if (apiToken) {
    const user = await findUserByApiToken(apiToken);
    if (user) {
      req.user = user;
      req.authType = "api_token";
      return next();
    }

    return res.status(401).json({
      error: "invalid_api_token",
      message: "유효하지 않거나 만료된 API 토큰입니다."
    });
  }

  if (accessToken) {
    return res.status(401).json({
      error: "invalid_token",
      message: "유효하지 않은 인증 토큰입니다."
    });
  }

  return res.status(401).json({
    error: "unauthorized",
    message: "로그인이 필요합니다."
  });
});

app.get("/api/health", (req, res) => {
  res.status(200).json({
    status: "ok",
    service: "sikdorak-api",
    uptimeSec: Math.floor(process.uptime()),
    timestamp: new Date().toISOString(),
    web: {
      quizAttemptPage: "/pages/quiz-attempt.html",
      build: process.env.PASSIO_WEB_BUILD || "20260418-quiz-attempt-onDemand",
      note:
        "브라우저에 이 build 값이 보이면 API는 최신입니다. 화면이 예전이면 Nginx 정적(pages, assets) 동기화와 nginx reload가 필요합니다."
    }
  });
});

app.post("/api/auth/register", asyncHandler(async (_req, res) => {
  return res.status(410).json({
    error: "auth_migrated",
    message: "회원가입은 https://auth.cortie.io/signup 에서만 가능합니다."
  });
}));

app.post("/api/auth/login", asyncHandler(async (_req, res) => {
  return res.status(410).json({
    error: "auth_migrated",
    message: "로그인은 https://auth.cortie.io/login 에서만 가능합니다."
  });
}));

app.post("/api/auth/refresh", asyncHandler(async (req, res) => {
  const refreshToken = req.cookies?.refresh_token;
  if (!refreshToken) {
    return res.status(401).json({
      error: "missing_refresh_token",
      message: "리프레시 토큰이 없습니다."
    });
  }

  let payload;
  try {
    payload = jwt.verify(refreshToken, JWT_REFRESH_SECRET);
  } catch (error) {
    clearAuthCookies(res);
    return res.status(401).json({
      error: "invalid_refresh_token",
      message: "리프레시 토큰이 유효하지 않습니다."
    });
  }

  if (payload.type !== "refresh" || !payload.jti) {
    return res.status(401).json({
      error: "invalid_refresh_token",
      message: "리프레시 토큰 형식이 올바르지 않습니다."
    });
  }

  const tokenRow = await findRefreshToken(payload.jti);
  if (!tokenRow || tokenRow.revoked_at || new Date(tokenRow.expires_at).getTime() < Date.now()) {
    clearAuthCookies(res);
    return res.status(401).json({
      error: "refresh_token_expired",
      message: "다시 로그인해주세요."
    });
  }

  const user = await findUserById(payload.sub);
  if (!user) {
    clearAuthCookies(res);
    return res.status(401).json({
      error: "user_not_found",
      message: "사용자를 찾을 수 없습니다."
    });
  }

  await revokeRefreshToken(payload.jti);

  const accessToken = createAccessToken(user);
  const { token: rotatedRefreshToken, jti: rotatedJti } = createRefreshToken(user);
  await storeRefreshToken({
    userId: user.id,
    tokenJti: rotatedJti,
    expiresAt: getRefreshExpiryDate()
  });

  setAuthCookies(res, accessToken, rotatedRefreshToken);

  return res.status(200).json({
    message: "refresh_success",
    user,
    accessToken
  });
}));

app.post("/api/auth/logout", asyncHandler(async (req, res) => {
  const refreshToken = req.cookies?.refresh_token;

  if (refreshToken) {
    try {
      const payload = jwt.verify(refreshToken, JWT_REFRESH_SECRET);
      if (payload?.jti) {
        await revokeRefreshToken(payload.jti);
      }
      if (payload?.sub) {
        await revokeAllRefreshTokensByUser(payload.sub);
      }
    } catch (error) {
      // Ignore invalid token during logout.
    }
  }

  clearAuthCookies(res);
  res.clearCookie(AUTH_COOKIE_NAME, { path: "/" });
  res.clearCookie(AUTH_COOKIE_NAME, { path: "/", domain: ".cortie.io" });
  return res.status(200).json({ message: "logout_success" });
}));

app.get("/api/auth/me", requireAuth, (req, res) => {
  return res.status(200).json({ user: req.user });
});

app.get("/pages/login.html", (_req, res) => {
  res.redirect(`${AUTH_SERVER_LOGIN_URL}?redirect_uri=${encodeURIComponent("https://passio.cortie.io/pages/dashboard.html")}`);
});

app.get("/pages/signup.html", (_req, res) => {
  res.redirect(`${AUTH_SERVER_SIGNUP_URL}?redirect_uri=${encodeURIComponent("https://passio.cortie.io/pages/dashboard.html")}`);
});

app.post("/api/auth/api-token/reveal", requireAuth, asyncHandler(async (req, res) => {
  const password = String(req.body?.password || "");
  if (!password) {
    return res.status(400).json({
      error: "invalid_input",
      message: "password는 필수입니다."
    });
  }

  const ok = await verifyUserPasswordById(req.user.id, password);
  if (!ok) {
    return res.status(401).json({
      error: "invalid_credentials",
      message: "비밀번호가 올바르지 않습니다."
    });
  }

  const tokenInfo = await issueOrGetApiTokenByUserId(req.user.id);
  return res.status(200).json({
    token: tokenInfo.token_value,
    preview: tokenInfo.token_preview,
    expiresAt: tokenInfo.expiresAt,
    createdAt: tokenInfo.createdAt,
    rotatedAt: tokenInfo.rotatedAt
  });
}));

app.get("/api/quiz/questions", requireAuth, asyncHandler(async (req, res) => {
  const rawQuestionId = req.query.questionId;
  if (rawQuestionId !== undefined) {
    const questionId = Number(rawQuestionId);
    if (!Number.isInteger(questionId) || questionId <= 0) {
      return res.status(400).json({
        error: "invalid_question_id",
        message: "유효한 questionId(양의 정수)가 필요합니다."
      });
    }

    const question = await getQuestionById(questionId);
    if (!question) {
      return res.status(404).json({
        error: "question_not_found",
        message: "해당 문제를 찾을 수 없습니다."
      });
    }

    return res.status(200).json({ questions: [question], total: 1 });
  }

  const questions = await getQuizQuestions();
  return res.status(200).json({ questions, total: questions.length });
}));

app.get("/api/question-bank/subjects", requireAuth, asyncHandler(async (req, res) => {
  const certificates = await getQuestionBankFilters();
  return res.status(200).json({ certificates, total: certificates.length });
}));

app.get("/api/question-bank/questions", requireAuth, asyncHandler(async (req, res) => {
  const certificate = typeof req.query.certificate === "string" ? req.query.certificate.trim() : "";
  const subject = typeof req.query.subject === "string" ? req.query.subject.trim() : "";
  const page = Number(req.query.page || 1);
  const pageSize = Number(req.query.pageSize || 20);

  const bank = await getQuestionBank({
    certificate: certificate || null,
    subject: subject || null,
    page,
    pageSize
  });

  return res.status(200).json({
    questions: bank.items,
    total: bank.total,
    page: bank.page,
    pageSize: bank.pageSize,
    totalPages: bank.totalPages
  });
}));

app.post("/api/quiz/attempts", requireAuth, asyncHandler(async (req, res) => {
  const rawAnswers = Array.isArray(req.body?.answers) ? req.body.answers : [];
  const durationSec = Math.max(0, Number(req.body?.durationSec) || 0);
  const quizId = String(req.body?.quizId || crypto.randomUUID()).trim();

  if (!rawAnswers.length) {
    return res.status(400).json({
      error: "invalid_input",
      message: "answers is required"
    });
  }

  if (rawAnswers.length > 500) {
    return res.status(400).json({
      error: "invalid_input",
      message: "too many answers"
    });
  }

  if (!quizId || quizId.length > 120) {
    return res.status(400).json({
      error: "invalid_input",
      message: "invalid quizId"
    });
  }

  const answers = rawAnswers.map(item => {
    const selectedIndex = item.selectedIndex === null || item.selectedIndex === undefined
      ? null
      : Number(item.selectedIndex);
    const correctIndex = Number(item.correctIndex);
    const isCorrect = selectedIndex !== null && selectedIndex === correctIndex;

    return {
      questionId: Number(item.questionId) || null,
      subject: String(item.subject || ""),
      questionText: String(item.questionText || ""),
      selectedIndex: selectedIndex,
      correctIndex: Number.isInteger(correctIndex) ? correctIndex : 0,
      isCorrect
    };
  });

  const totalQuestions = answers.length;
  const correctCount = answers.filter(x => x.isCorrect).length;
  const score = Math.round((correctCount / totalQuestions) * 100);

  const saved = await saveQuizAttempt({
    userId: req.user.id,
    quizUid: quizId,
    totalQuestions,
    correctCount,
    score,
    durationSec,
    answers
  });

  return res.status(201).json({
    message: "attempt_saved",
    quizId,
    attemptId: saved.id,
    createdAt: saved.createdAt,
    totalQuestions,
    correctCount,
    score
  });
}));

app.get("/api/quiz/history", requireAuth, asyncHandler(async (req, res) => {
  const limit = Math.min(Math.max(Number(req.query.limit) || 100, 1), 500);
  const offset = Math.min(Math.max(Number(req.query.offset) || 0, 0), 100_000);
  const attempts = await getQuizHistoryByUser(req.user.id, limit, offset);
  return res.status(200).json({
    attempts,
    hasMore: attempts.length === limit,
    limit,
    offset
  });
}));

app.get("/api/quiz/history/:attemptId/pdf", requireAuth, asyncHandler(async (req, res) => {
  const attemptId = Number(req.params.attemptId);
  if (!Number.isInteger(attemptId) || attemptId <= 0) {
    return res.status(400).json({
      error: "invalid_attempt_id",
      message: "유효한 attemptId가 필요합니다."
    });
  }

  const detail = await getQuizAttemptDetail(req.user.id, attemptId);
  if (!detail) {
    return res.status(404).json({
      error: "attempt_not_found",
      message: "해당 기록을 찾을 수 없습니다."
    });
  }

  const readiness = computePdfReadiness(detail);
  if (!readiness.total) {
    return res.status(400).json({
      error: "no_answers",
      message: "답안이 없어 PDF를 만들 수 없습니다."
    });
  }
  if (!readiness.ok) {
    return res.status(409).json({
      error: "incomplete_ai_explains",
      message: `오답 문항의 AI 해설이 모두 있어야 PDF를 받을 수 있습니다. 아직 없는 문항: ${readiness.missingOneBased.join(", ")}번`,
      missingQuestions: readiness.missingOneBased
    });
  }

  try {
    const pdf = await buildQuizAttemptPdfBuffer(detail);
    const filename = `passio-quiz-${attemptId}.pdf`;
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="${filename}"; filename*=UTF-8''${encodeURIComponent(filename)}`);
    res.setHeader("Cache-Control", "private, no-store");
    return res.status(200).send(pdf);
  } catch (err) {
    const msg = err && err.message ? String(err.message) : "pdf_build_failed";
    return res.status(503).json({
      error: "pdf_build_failed",
      message: msg
    });
  }
}));

app.get("/api/quiz/history/:attemptId", requireAuth, asyncHandler(async (req, res) => {
  const attemptId = Number(req.params.attemptId);
  if (!Number.isInteger(attemptId) || attemptId <= 0) {
    return res.status(400).json({
      error: "invalid_attempt_id",
      message: "유효한 attemptId가 필요합니다."
    });
  }

  const detail = await getQuizAttemptDetail(req.user.id, attemptId);
  if (!detail) {
    return res.status(404).json({
      error: "attempt_not_found",
      message: "해당 기록을 찾을 수 없습니다."
    });
  }

  return res.status(200).json({ attempt: detail });
}));


// ── RAG API 프록시 ──────────────────────────────────────────────────────────
const RAG_API_URL = process.env.RAG_API_URL || "http://127.0.0.1:8001";
const RAG_PROXY_TIMEOUT_MS = Math.max(60_000, Number(process.env.RAG_PROXY_TIMEOUT_MS || 900_000));

/**
 * Python RAG 호출 동시 실행 수 제한(슬라이딩) + 대기열 최대 길이.
 * 여러 사용자가 동시에 많은 job을 올려도 메모리·스레드 폭주를 막음.
 * RAG_SOLVE_MAX_CONCURRENCY 기본 2 (1~8), RAG_SOLVE_MAX_QUEUE 기본 200
 */
function createConcurrencyLimit(limit, maxQueueDepth) {
  let active = 0;
  const queue = [];
  function tryNext() {
    if (active >= limit) {
      return;
    }
    const item = queue.shift();
    if (!item) {
      return;
    }
    active += 1;
    const { fn, resolve, reject } = item;
    Promise.resolve()
      .then(fn)
      .then(resolve, reject)
      .finally(() => {
        active -= 1;
        tryNext();
      });
  }
  return fn =>
    new Promise((resolve, reject) => {
      if (queue.length >= maxQueueDepth) {
        const e = new Error("rag_queue_full");
        e.statusCode = 503;
        reject(e);
        return;
      }
      queue.push({ fn, resolve, reject });
      tryNext();
    });
}

const RAG_SOLVE_MAX_CONCURRENCY = Math.max(1, Math.min(8, Number(process.env.RAG_SOLVE_MAX_CONCURRENCY || 2)));
const RAG_SOLVE_MAX_QUEUE = Math.max(
  RAG_SOLVE_MAX_CONCURRENCY,
  Math.min(500, Number(process.env.RAG_SOLVE_MAX_QUEUE || 200))
);
const runRagSolveWithConcurrencyLimit = createConcurrencyLimit(RAG_SOLVE_MAX_CONCURRENCY, RAG_SOLVE_MAX_QUEUE);

const RAG_FETCH_RETRIES = Math.max(1, Math.min(8, Number(process.env.RAG_FETCH_RETRIES || 4)));

async function callRagServiceOnce(items, rebuildDb = false) {
  let ragRes;
  try {
    ragRes = await fetch(`${RAG_API_URL}/api/v1/rag/solve`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ items, rebuild_db: rebuildDb }),
      signal: AbortSignal.timeout(RAG_PROXY_TIMEOUT_MS)
    });
  } catch (err) {
    const e = new Error("rag_unavailable");
    e.statusCode = 502;
    e.cause = err;
    throw e;
  }

  if (!ragRes.ok) {
    const e = new Error("rag_solve_http_error");
    e.statusCode = ragRes.status;
    try {
      e.responsePayload = await ragRes.json();
    } catch {
      e.responsePayload = { message: await ragRes.text() };
    }
    throw e;
  }

  return ragRes.json();
}

/** RAG API 일시 연결 실패 시 짧게 재시도 (대량 job·프로세스 재시작 구간 완화) */
async function callRagService(items, rebuildDb = false) {
  let lastErr;
  for (let attempt = 1; attempt <= RAG_FETCH_RETRIES; attempt += 1) {
    try {
      return await callRagServiceOnce(items, rebuildDb);
    } catch (err) {
      lastErr = err;
      if (!err || err.message !== "rag_unavailable") {
        throw err;
      }
      if (attempt >= RAG_FETCH_RETRIES) {
        break;
      }
      const delayMs = Math.min(8000, 400 * 2 ** (attempt - 1));
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }
  throw lastErr;
}

async function processRagSolveJob(jobId) {
  const safeId = Number(jobId);
  if (!Number.isInteger(safeId) || safeId <= 0) {
    return;
  }

  await markRagSolveJobProcessing(safeId);
  const job = await getRagSolveJobById(safeId);
  if (!job) {
    return;
  }

  let rebuildDb = false;
  try {
    const payload =
      typeof job.requestPayload === "string" ? JSON.parse(job.requestPayload) : job.requestPayload;
    rebuildDb = Boolean(payload?.rebuild_db);
  } catch {
    rebuildDb = false;
  }

  const opts = [job.option1, job.option2, job.option3, job.option4].map(value => String(value || "").trim());
  const item = {
    q: String(job.questionText || "").trim(),
    opts: makeRagOptionString(opts),
    wrong: formatRagChoice(job.wrongChoice, opts),
    ans: formatRagChoice(job.answerChoice, opts)
  };

  try {
    const data = await runRagSolveWithConcurrencyLimit(() => callRagService([item], rebuildDb));
    const resultPayload = {
      ok: Boolean(data?.ok),
      total: data?.total ?? 0,
      results: data?.results ?? []
    };
    await completeRagSolveJob(safeId, resultPayload);
  } catch (err) {
    if (err && err.message === "rag_queue_full") {
      await failRagSolveJob(
        safeId,
        "서버 해설 처리 대기열이 가득 찼습니다. 잠시 후 히스토리에서 다시 시도해 주세요."
      );
      return;
    }
    const msg =
      err && err.message === "rag_unavailable"
        ? "RAG 서버에 일시적으로 연결하지 못했습니다. 잠시 후 히스토리에서 해당 문항만 다시 시도해 주세요."
        : err?.responsePayload?.message ||
          err?.responsePayload?.detail ||
          err?.message ||
          "rag_job_failed";
    await failRagSolveJob(safeId, String(msg));
  }
}

app.post("/api/rag2/jobs", requireAuth, rag2JobGlobalLimiter, rag2JobUserLimiter, asyncHandler(async (req, res) => {
  const { question, options, wrongChoice, answerChoice, rebuildDb } = normalizeRagSolveInput(req.body);
  const rawAttempt = req.body.attemptId;
  const attemptNum = rawAttempt != null && String(rawAttempt).trim() !== "" ? Number(rawAttempt) : NaN;
  const quizAttemptId = Number.isInteger(attemptNum) && attemptNum > 0 ? attemptNum : null;

  let quizAttemptAnswerIndex = null;
  if (req.body.answerIndex !== undefined && req.body.answerIndex !== null && String(req.body.answerIndex).trim() !== "") {
    const ai = Number(req.body.answerIndex);
    if (Number.isInteger(ai) && ai >= 0) {
      quizAttemptAnswerIndex = ai;
    }
  }

  if (!question) return res.status(400).json({ error: "invalid_input", message: "문제 본문을 입력해주세요." });
  if (options.length !== 4 || options.some(x => !x)) return res.status(400).json({ error: "invalid_input", message: "보기 4개를 모두 입력해주세요." });
  const job = await createRagSolveJob({
    userId: req.user.id,
    questionText: question,
    options,
    wrongChoice: wrongChoice || null,
    answerChoice: answerChoice || null,
    quizAttemptId,
    quizAttemptAnswerIndex,
    requestPayload: {
      question,
      options,
      wrongChoice: wrongChoice || null,
      answerChoice: answerChoice || null,
      rebuild_db: rebuildDb,
      attemptId: quizAttemptId,
      answerIndex: quizAttemptAnswerIndex
    }
  });
  setImmediate(() => processRagSolveJob(job.id).catch(err => console.error("rag_job_failed", job.id, err)));
  return res.status(202).json({ message: "rag_job_accepted", jobId: job.id, status: job.status, createdAt: job.createdAt });
}));
// ...existing code...

app.get("/api/rag/jobs/:jobId", requireAuth, asyncHandler(async (req, res) => {
  const jobId = Number(req.params.jobId);
  if (!Number.isInteger(jobId) || jobId <= 0) {
    return res.status(400).json({
      error: "invalid_job_id",
      message: "유효한 jobId가 필요합니다."
    });
  }

  const job = await getRagSolveJobDetail(req.user.id, jobId);
  if (!job) {
    return res.status(404).json({
      error: "job_not_found",
      message: "해당 AI 해설 기록을 찾을 수 없습니다."
    });
  }

  return res.status(200).json({ job });
}));

app.get("/api/rag/history", requireAuth, asyncHandler(async (req, res) => {
  const limit = Math.min(Math.max(Number(req.query.limit) || 100, 1), 500);
  const offset = Math.min(Math.max(Number(req.query.offset) || 0, 0), 100_000);
  const jobs = await getRagSolveHistoryByUser(req.user.id, limit, offset);
  return res.status(200).json({
    jobs,
    hasMore: jobs.length === limit,
    limit,
    offset
  });
}));

app.post(
  "/api/rag/solve",
  requireAuthOrApiToken,
  ragSolveDirectGlobalLimiter,
  ragSolveDirectUserLimiter,
  asyncHandler(async (req, res) => {
  const items = Array.isArray(req.body?.items) ? req.body.items : [];
  const rebuildDb = Boolean(req.body?.rebuild_db);

  if (!items.length) {
    return res.status(400).json({
      error: "invalid_input",
      message: "items 배열이 필요합니다."
    });
  }

  const maxItems = Math.max(1, Math.min(50, Number(process.env.RAG_SOLVE_MAX_ITEMS || 25)));
  if (items.length > maxItems) {
    return res.status(400).json({
      error: "invalid_input",
      message: `한 번에 최대 ${maxItems}개까지 처리할 수 있습니다.`
    });
  }

  try {
    const data = await runRagSolveWithConcurrencyLimit(() => callRagService(items, rebuildDb));
    return res.status(200).json(data);
  } catch (err) {
    return res.status(err.statusCode || 502).json(
      err.responsePayload || {
        error: "rag_unavailable",
        message: "RAG 서비스에 연결할 수 없습니다."
      }
    );
  }
}));

app.use("/api", (req, res) => {
  res.status(404).json({
    error: "not_found",
    message: "Requested API route does not exist"
  });
});

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({
    error: "internal_server_error",
    requestId: req.requestId
  });
});

async function startServer() {
  await initDatabase();
  await purgeExpiredRefreshTokens();

  app.listen(PORT, "127.0.0.1", () => {
    console.log(`sikdorak-api listening on 127.0.0.1:${PORT}`);
  });
}

startServer().catch((error) => {
  console.error("failed_to_start_server", error);
  process.exit(1);
});
