const express = require("express");
const helmet = require("helmet");
const cors = require("cors");
const compression = require("compression");
const morgan = require("morgan");
const rateLimit = require("express-rate-limit");
const crypto = require("node:crypto");
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

const app = express();
const PORT = Number(process.env.PORT || 3100);
const ALLOWED_ORIGIN = process.env.ALLOWED_ORIGIN || "*";
const JWT_ACCESS_SECRET = process.env.JWT_ACCESS_SECRET || "dev_access_secret_change_me";
const JWT_REFRESH_SECRET = process.env.JWT_REFRESH_SECRET || "dev_refresh_secret_change_me";
const ACCESS_TOKEN_EXPIRES = process.env.ACCESS_TOKEN_EXPIRES || "15m";
const REFRESH_TOKEN_EXPIRES_DAYS = Number(process.env.REFRESH_TOKEN_EXPIRES_DAYS || 14);
const IS_PROD = process.env.NODE_ENV === "production";

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
    timestamp: new Date().toISOString()
  });
});

app.post("/api/auth/register", asyncHandler(async (req, res) => {
  const username = String(req.body?.username || "").trim().toLowerCase();
  const email = String(req.body?.email || "").trim().toLowerCase();
  const password = String(req.body?.password || "");
  const name = String(req.body?.name || "").trim();
  const studentNumber = String(req.body?.studentNumber || req.body?.student_number || "").trim();

  if (!username || !email || !password || !name || !studentNumber) {
    return res.status(400).json({
      error: "invalid_input",
      message: "username, name, studentNumber, email and password are required"
    });
  }

  if (!/^[a-z0-9_]{3,30}$/.test(username)) {
    return res.status(400).json({
      error: "invalid_username",
      message: "아이디는 영문 소문자, 숫자, 밑줄(_) 3~30자로 입력해주세요."
    });
  }

  if (password.length < 8) {
    return res.status(400).json({
      error: "weak_password",
      message: "비밀번호는 8자 이상이어야 합니다."
    });
  }

  if (studentNumber.length < 4 || studentNumber.length > 30) {
    return res.status(400).json({
      error: "invalid_student_number",
      message: "학번은 4자 이상 30자 이하로 입력해주세요."
    });
  }

  const existing = await findUserByEmail(email);
  if (existing) {
    return res.status(409).json({
      error: "email_exists",
      message: "이미 가입된 이메일입니다."
    });
  }

  const existingUsername = await findUserByUsername(normalizeUsername(username));
  if (existingUsername) {
    return res.status(409).json({
      error: "username_exists",
      message: "이미 사용 중인 아이디입니다."
    });
  }

  const user = await createUser({ username, email, name, password, studentNumber });

  return res.status(201).json({
    message: "register_success",
    user
  });
}));

app.post("/api/auth/login", asyncHandler(async (req, res) => {
  const username = String(req.body?.username || "").trim().toLowerCase();
  const password = String(req.body?.password || "");

  if (!username || !password) {
    return res.status(400).json({
      error: "invalid_input",
      message: "username and password are required"
    });
  }

  const user = await verifyUser(normalizeUsername(username), password);
  if (!user) {
    return res.status(401).json({
      error: "invalid_credentials",
      message: "아이디 또는 비밀번호가 올바르지 않습니다."
    });
  }

  const accessToken = createAccessToken(user);
  const { token: refreshToken, jti } = createRefreshToken(user);
  await storeRefreshToken({
    userId: user.id,
    tokenJti: jti,
    expiresAt: getRefreshExpiryDate()
  });
  setAuthCookies(res, accessToken, refreshToken);

  return res.status(200).json({
    message: "login_success",
    user,
    accessToken
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
  return res.status(200).json({ message: "logout_success" });
}));

app.get("/api/auth/me", requireAuth, (req, res) => {
  return res.status(200).json({ user: req.user });
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
  const limit = Number(req.query.limit || 100);
  const attempts = await getQuizHistoryByUser(req.user.id, limit);
  return res.status(200).json({ attempts, total: attempts.length });
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

async function callRagService(items, rebuildDb = false) {
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
    throw e;
  }

  const data = await ragRes.json();
  if (!ragRes.ok) {
    const e = new Error(data?.message || "rag_request_failed");
    e.statusCode = ragRes.status;
    e.responsePayload = data;
    throw e;
  }

  return data;
}

async function processRagSolveJob(jobId) {
  const job = await getRagSolveJobById(jobId);
  if (!job) {
    return;
  }

  await markRagSolveJobProcessing(jobId);

  const options = [job.option1, job.option2, job.option3, job.option4];
  const item = {
    q: job.questionText,
    opts: makeRagOptionString(options),
    wrong: formatRagChoice(job.wrongChoice, options),
    ans: formatRagChoice(job.answerChoice, options)
  };

  try {
    const responsePayload = await callRagService([item], Boolean(job.requestPayload?.rebuild_db));
    await completeRagSolveJob(jobId, responsePayload);
  } catch (error) {
    const errorText = error?.responsePayload?.message || error?.message || "rag_processing_failed";
    await failRagSolveJob(jobId, errorText);
  }
}

app.post("/api/rag/jobs", requireAuth, asyncHandler(async (req, res) => {
  const { question, options, wrongChoice, answerChoice, rebuildDb } = normalizeRagSolveInput(req.body);

  if (!question) {
    return res.status(400).json({
      error: "invalid_input",
      message: "문제 본문을 입력해주세요."
    });
  }

  if (options.length !== 4 || options.some(x => !x)) {
    return res.status(400).json({
      error: "invalid_input",
      message: "보기 4개를 모두 입력해주세요."
    });
  }

  const job = await createRagSolveJob({
    userId: req.user.id,
    questionText: question,
    options,
    wrongChoice: wrongChoice || null,
    answerChoice: answerChoice || null,
    requestPayload: {
      question,
      options,
      wrongChoice: wrongChoice || null,
      answerChoice: answerChoice || null,
      rebuild_db: rebuildDb
    }
  });

  setImmediate(() => {
    processRagSolveJob(job.id).catch(err => {
      console.error("rag_job_failed", job.id, err);
    });
  });

  return res.status(202).json({
    message: "rag_job_accepted",
    jobId: job.id,
    status: job.status,
    createdAt: job.createdAt
  });
}));

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
  const limit = Number(req.query.limit || 100);
  const jobs = await getRagSolveHistoryByUser(req.user.id, limit);
  return res.status(200).json({ jobs, total: jobs.length });
}));

app.post("/api/rag/solve", requireAuthOrApiToken, asyncHandler(async (req, res) => {
  const items = Array.isArray(req.body?.items) ? req.body.items : [];
  const rebuildDb = Boolean(req.body?.rebuild_db);

  if (!items.length) {
    return res.status(400).json({
      error: "invalid_input",
      message: "items 배열이 필요합니다."
    });
  }

  if (items.length > 50) {
    return res.status(400).json({
      error: "invalid_input",
      message: "한 번에 최대 50개까지 처리할 수 있습니다."
    });
  }

  try {
    const data = await callRagService(items, rebuildDb);
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

app.use((req, res) => {
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
