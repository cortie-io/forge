const { Pool } = require("pg");
const bcrypt = require("bcryptjs");
const crypto = require("node:crypto");

const DATABASE_URL =
  process.env.DATABASE_URL || "postgresql://sikdorak_app:sikdorak_password@127.0.0.1:5432/sikdorak";
const API_TOKEN_EXPIRES_DAYS = Number(process.env.API_TOKEN_EXPIRES_DAYS || 30);

const pool = new Pool({ connectionString: DATABASE_URL });

async function initDatabase() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS users (
      id BIGSERIAL PRIMARY KEY,
      username TEXT UNIQUE,
      email TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      student_number TEXT,
      password_hash TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);

  await pool.query("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT");
  await pool.query("ALTER TABLE users ADD COLUMN IF NOT EXISTS student_number TEXT");
  await pool.query(
    "CREATE UNIQUE INDEX IF NOT EXISTS users_username_unique_idx ON users (username) WHERE username IS NOT NULL"
  );

  await pool.query(`
    CREATE TABLE IF NOT EXISTS refresh_tokens (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      token_jti TEXT NOT NULL UNIQUE,
      expires_at TIMESTAMPTZ NOT NULL,
      revoked_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);

  await pool.query(`
    CREATE TABLE IF NOT EXISTS user_api_tokens (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
      token_hash TEXT NOT NULL UNIQUE,
      token_value TEXT NOT NULL UNIQUE,
      token_preview TEXT NOT NULL,
      expires_at TIMESTAMPTZ NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      rotated_at TIMESTAMPTZ,
      last_used_at TIMESTAMPTZ
    )
  `);
  await pool.query("CREATE INDEX IF NOT EXISTS user_api_tokens_expires_idx ON user_api_tokens (expires_at)");

  await pool.query(`
    CREATE TABLE IF NOT EXISTS questions (
      id BIGSERIAL PRIMARY KEY,
      subject TEXT NOT NULL,
      question TEXT NOT NULL,
      option1 TEXT NOT NULL,
      option2 TEXT NOT NULL,
      option3 TEXT NOT NULL,
      option4 TEXT NOT NULL,
      answer SMALLINT NOT NULL CHECK (answer BETWEEN 1 AND 4)
    )
  `);
  await pool.query(`CREATE INDEX IF NOT EXISTS questions_subject_idx ON questions (subject)`);

  await pool.query(`
    CREATE TABLE IF NOT EXISTS quiz_attempts (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      quiz_uid TEXT,
      total_questions INTEGER NOT NULL,
      correct_count INTEGER NOT NULL,
      score INTEGER NOT NULL,
      duration_sec INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
  await pool.query("ALTER TABLE quiz_attempts ADD COLUMN IF NOT EXISTS quiz_uid TEXT");

  await pool.query(`
    CREATE TABLE IF NOT EXISTS quiz_attempt_answers (
      id BIGSERIAL PRIMARY KEY,
      attempt_id BIGINT NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
      question_id BIGINT,
      subject TEXT,
      question_text TEXT,
      selected_index SMALLINT,
      correct_index SMALLINT NOT NULL,
      is_correct BOOLEAN NOT NULL
    )
  `);

  await pool.query(`
    CREATE TABLE IF NOT EXISTS rag_solve_jobs (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'pending',
      question_text TEXT NOT NULL,
      option_1 TEXT NOT NULL,
      option_2 TEXT NOT NULL,
      option_3 TEXT NOT NULL,
      option_4 TEXT NOT NULL,
      wrong_choice TEXT,
      answer_choice TEXT,
      request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
      result_payload JSONB,
      error_message TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      started_at TIMESTAMPTZ,
      completed_at TIMESTAMPTZ
    )
  `);
  await pool.query("CREATE INDEX IF NOT EXISTS rag_solve_jobs_user_idx ON rag_solve_jobs (user_id, created_at DESC)");
  await pool.query("CREATE INDEX IF NOT EXISTS rag_solve_jobs_status_idx ON rag_solve_jobs (status, created_at DESC)");

  // Legacy rows may contain deleted/invalid question ids; null them before adding FK.
  await pool.query(`
    UPDATE quiz_attempt_answers qa
    SET question_id = NULL
    WHERE question_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM questions q WHERE q.id = qa.question_id
      )
  `);

  await pool.query(`
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'quiz_attempt_answers_question_id_fkey'
      ) THEN
        ALTER TABLE quiz_attempt_answers
          ADD CONSTRAINT quiz_attempt_answers_question_id_fkey
          FOREIGN KEY (question_id)
          REFERENCES questions(id)
          ON DELETE SET NULL;
      END IF;
    END
    $$;
  `);

  await pool.query("CREATE INDEX IF NOT EXISTS quiz_attempts_user_idx ON quiz_attempts (user_id, created_at DESC)");
  await pool.query("CREATE INDEX IF NOT EXISTS quiz_attempt_answers_attempt_idx ON quiz_attempt_answers (attempt_id)");
  await pool.query("CREATE INDEX IF NOT EXISTS quiz_attempt_answers_question_idx ON quiz_attempt_answers (question_id)");

  await ensureUsernamesForLegacyUsers();
}

async function getQuizQuestions() {
  const specs = [
    { subject: "1과목 TCP/IP", n: 17 },
    { subject: "2과목 네트워크 일반", n: 10 },
    { subject: "3과목 NOS", n: 18 },
    { subject: "4과목 네트워크 운용기기", n: 5 }
  ];

  const rows = [];
  for (const { subject, n } of specs) {
    const result = await pool.query(
      `SELECT id, subject, question, option1, option2, option3, option4, answer
       FROM questions WHERE subject = $1 ORDER BY RANDOM() LIMIT $2`,
      [subject, n]
    );
    rows.push(...result.rows);
  }

  // Fisher-Yates shuffle
  for (let i = rows.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [rows[i], rows[j]] = [rows[j], rows[i]];
  }

  return rows.map(r => ({
    id: r.id,
    subject: r.subject,
    question: r.question,
    options: [r.option1, r.option2, r.option3, r.option4],
    answer: r.answer - 1  // 0-indexed
  }));
}

async function getQuestionById(questionId) {
  const safeId = Number(questionId);
  if (!Number.isInteger(safeId) || safeId <= 0) {
    return null;
  }

  const result = await pool.query(
    `SELECT id, subject, question, option1, option2, option3, option4, answer
     FROM questions
     WHERE id = $1
     LIMIT 1`,
    [safeId]
  );

  const row = result.rows[0];
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    subject: row.subject,
    question: row.question,
    options: [row.option1, row.option2, row.option3, row.option4],
    answer: row.answer - 1
  };
}

function inferCertificateFromSubject(subject) {
  const s = String(subject || "").trim();
  if (!s) {
    return "기타";
  }

  if (/^\d+과목\s/.test(s)) {
    return "네트워크 관리사 2급";
  }

  if (s.includes("::")) {
    const [certificate] = s.split("::");
    return String(certificate || "").trim() || "기타";
  }

  return "기타";
}

function inferSubSubjectLabel(subject) {
  const s = String(subject || "").trim();
  if (!s) {
    return "미분류";
  }

  if (s.includes("::")) {
    const [, subSubject] = s.split("::");
    return String(subSubject || "").trim() || s;
  }

  return s;
}

async function getQuestionBankFilters() {
  const result = await pool.query(
    `SELECT subject, COUNT(*)::INT AS count
     FROM questions
     GROUP BY subject
     ORDER BY subject ASC`
  );

  const byCertificate = new Map();

  for (const row of result.rows) {
    const rawSubject = String(row.subject || "").trim();
    const count = Number(row.count) || 0;
    const certificate = inferCertificateFromSubject(rawSubject);
    const subSubject = inferSubSubjectLabel(rawSubject);

    if (!byCertificate.has(certificate)) {
      byCertificate.set(certificate, {
        name: certificate,
        count: 0,
        subjects: []
      });
    }

    const certItem = byCertificate.get(certificate);
    certItem.count += count;
    certItem.subjects.push({
      label: subSubject,
      value: rawSubject,
      count
    });
  }

  const certificates = Array.from(byCertificate.values()).sort((a, b) => a.name.localeCompare(b.name, "ko"));
  for (const cert of certificates) {
    cert.subjects.sort((a, b) => a.label.localeCompare(b.label, "ko"));
  }

  return certificates;
}

async function getQuestionBank({ certificate = null, subject = null, page = 1, pageSize = 20 } = {}) {
  const safePage = Math.max(1, Number(page) || 1);
  const safePageSize = Math.min(Math.max(Number(pageSize) || 20, 1), 100);

  const safeSubject = typeof subject === "string" ? subject.trim() : "";
  const safeCertificate = typeof certificate === "string" ? certificate.trim() : "";

  let filteredSubjects = null;
  if (safeSubject) {
    filteredSubjects = [safeSubject];
  } else if (safeCertificate) {
    const filters = await getQuestionBankFilters();
    const cert = filters.find(item => item.name === safeCertificate);
    filteredSubjects = cert ? cert.subjects.map(item => item.value) : [];
  }

  if (Array.isArray(filteredSubjects) && filteredSubjects.length === 0) {
    return {
      items: [],
      total: 0,
      page: 1,
      pageSize: safePageSize,
      totalPages: 1
    };
  }

  const whereSql = Array.isArray(filteredSubjects) ? "WHERE subject = ANY($1::text[])" : "";
  const whereParams = Array.isArray(filteredSubjects) ? [filteredSubjects] : [];

  const totalResult = await pool.query(
    `SELECT COUNT(*)::INT AS total
     FROM questions
     ${whereSql}`,
    whereParams
  );

  const total = Number(totalResult.rows[0]?.total) || 0;
  const totalPages = total === 0 ? 1 : Math.ceil(total / safePageSize);
  const currentPage = Math.min(safePage, totalPages);
  const currentOffset = (currentPage - 1) * safePageSize;

  const listParams = Array.isArray(filteredSubjects)
    ? [filteredSubjects, safePageSize, currentOffset]
    : [safePageSize, currentOffset];
  const listSql = Array.isArray(filteredSubjects)
    ? `SELECT id, subject, question
       FROM questions
       WHERE subject = ANY($1::text[])
       ORDER BY id ASC
       LIMIT $2 OFFSET $3`
    : `SELECT id, subject, question
       FROM questions
       ORDER BY id ASC
       LIMIT $1 OFFSET $2`;

  const result = await pool.query(listSql, listParams);

  const items = result.rows.map(row => ({
    id: row.id,
    certificate: inferCertificateFromSubject(row.subject),
    subject: row.subject,
    subSubject: inferSubSubjectLabel(row.subject),
    question: row.question
  }));

  return {
    items,
    total,
    page: currentPage,
    pageSize: safePageSize,
    totalPages
  };
}

function normalizeUsername(username) {
  return String(username)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "")
    .slice(0, 30);
}

function getApiTokenExpiryDate() {
  return new Date(Date.now() + API_TOKEN_EXPIRES_DAYS * 24 * 60 * 60 * 1000);
}

function createApiTokenValue() {
  return `psk_${crypto.randomBytes(32).toString("base64url")}`;
}

function hashApiToken(rawToken) {
  return crypto.createHash("sha256").update(String(rawToken)).digest("hex");
}

async function findUserByUsername(username) {
  const normalized = normalizeUsername(username);
  if (!normalized) {
    return null;
  }

  const result = await pool.query(
    "SELECT id, username, email, name, student_number AS \"studentNumber\", password_hash FROM users WHERE username = $1",
    [normalized]
  );

  return result.rows[0] || null;
}

async function findUserById(id) {
  const result = await pool.query(
    "SELECT id, username, email, name, student_number AS \"studentNumber\" FROM users WHERE id = $1",
    [id]
  );
  return result.rows[0] || null;
}

async function ensureUniqueUsername(candidate, fallbackPrefix = "user") {
  const base = normalizeUsername(candidate) || fallbackPrefix;
  let next = base;
  let suffix = 1;

  while (await findUserByUsername(next)) {
    suffix += 1;
    next = `${base}${suffix}`;
  }

  return next;
}

async function ensureUsernamesForLegacyUsers() {
  const result = await pool.query(
    "SELECT id, email FROM users WHERE username IS NULL OR username = '' ORDER BY id"
  );

  for (const row of result.rows) {
    const base = String(row.email || "").split("@")[0] || `user${row.id}`;
    const username = await ensureUniqueUsername(base, `user${row.id}`);
    await pool.query("UPDATE users SET username = $1 WHERE id = $2", [username, row.id]);
  }
}

async function createUser({ username, email, name, password, studentNumber }) {
  const normalizedUsername = normalizeUsername(username);
  const normalizedEmail = String(email).trim().toLowerCase();
  const safeName = String(name).trim();
  const safeStudentNumber = String(studentNumber).trim();
  const hash = await bcrypt.hash(String(password), 12);

  const uniqueUsername = await ensureUniqueUsername(normalizedUsername || normalizedEmail.split("@")[0]);

  const result = await pool.query(
    "INSERT INTO users (username, email, name, student_number, password_hash) VALUES ($1, $2, $3, $4, $5) RETURNING id, username, student_number AS \"studentNumber\"",
    [uniqueUsername, normalizedEmail, safeName, safeStudentNumber, hash]
  );

  return {
    id: result.rows[0].id,
    username: result.rows[0].username,
    studentNumber: result.rows[0].studentNumber,
    email: normalizedEmail,
    name: safeName
  };
}

async function findUserByEmail(email) {
  const normalizedEmail = String(email).trim().toLowerCase();
  const result = await pool.query(
    "SELECT id, username, email, name, student_number AS \"studentNumber\", password_hash FROM users WHERE email = $1",
    [normalizedEmail]
  );
  return result.rows[0] || null;
}

async function verifyUser(username, password) {
  const user = await findUserByUsername(username);
  if (!user) {
    return null;
  }

  const ok = await bcrypt.compare(String(password), user.password_hash);
  if (!ok) {
    return null;
  }

  return {
    id: user.id,
    username: user.username,
    email: user.email,
    name: user.name,
    studentNumber: user.studentNumber
  };
}

async function verifyUserPasswordById(userId, password) {
  const result = await pool.query(
    "SELECT password_hash FROM users WHERE id = $1",
    [userId]
  );

  const row = result.rows[0];
  if (!row?.password_hash) {
    return false;
  }

  return bcrypt.compare(String(password), row.password_hash);
}

async function issueOrGetApiTokenByUserId(userId) {
  const existingResult = await pool.query(
    `SELECT id, token_value, token_preview, expires_at AS "expiresAt", created_at AS "createdAt", rotated_at AS "rotatedAt"
     FROM user_api_tokens
     WHERE user_id = $1
     LIMIT 1`,
    [userId]
  );

  const existing = existingResult.rows[0] || null;
  if (existing && new Date(existing.expiresAt).getTime() > Date.now()) {
    return existing;
  }

  const tokenValue = createApiTokenValue();
  const tokenHash = hashApiToken(tokenValue);
  const tokenPreview = `${tokenValue.slice(0, 10)}...${tokenValue.slice(-6)}`;
  const expiresAt = getApiTokenExpiryDate();

  const saveResult = await pool.query(
    `INSERT INTO user_api_tokens (user_id, token_hash, token_value, token_preview, expires_at)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (user_id)
     DO UPDATE SET
       token_hash = EXCLUDED.token_hash,
       token_value = EXCLUDED.token_value,
       token_preview = EXCLUDED.token_preview,
       expires_at = EXCLUDED.expires_at,
       rotated_at = NOW()
     RETURNING token_value, token_preview, expires_at AS "expiresAt", created_at AS "createdAt", rotated_at AS "rotatedAt"`,
    [userId, tokenHash, tokenValue, tokenPreview, expiresAt]
  );

  return saveResult.rows[0];
}

async function findUserByApiToken(rawToken) {
  const safeToken = String(rawToken || "").trim();
  if (!safeToken || safeToken.length < 20) {
    return null;
  }

  const tokenHash = hashApiToken(safeToken);
  const result = await pool.query(
    `SELECT t.id AS "tokenId", t.expires_at AS "tokenExpiresAt",
            u.id, u.username, u.email, u.name, u.student_number AS "studentNumber"
     FROM user_api_tokens t
     INNER JOIN users u ON u.id = t.user_id
     WHERE t.token_hash = $1
       AND t.expires_at > NOW()
     LIMIT 1`,
    [tokenHash]
  );

  const row = result.rows[0] || null;
  if (!row) {
    return null;
  }

  await pool.query("UPDATE user_api_tokens SET last_used_at = NOW() WHERE id = $1", [row.tokenId]);

  return {
    id: row.id,
    username: row.username,
    email: row.email,
    name: row.name,
    studentNumber: row.studentNumber,
    tokenExpiresAt: row.tokenExpiresAt
  };
}

async function storeRefreshToken({ userId, tokenJti, expiresAt }) {
  await pool.query(
    "INSERT INTO refresh_tokens (user_id, token_jti, expires_at) VALUES ($1, $2, $3)",
    [userId, tokenJti, expiresAt]
  );
}

async function findRefreshToken(tokenJti) {
  const result = await pool.query(
    "SELECT id, user_id, token_jti, expires_at, revoked_at FROM refresh_tokens WHERE token_jti = $1",
    [tokenJti]
  );
  return result.rows[0] || null;
}

async function revokeRefreshToken(tokenJti) {
  await pool.query(
    "UPDATE refresh_tokens SET revoked_at = NOW() WHERE token_jti = $1 AND revoked_at IS NULL",
    [tokenJti]
  );
}

async function revokeAllRefreshTokensByUser(userId) {
  await pool.query(
    "UPDATE refresh_tokens SET revoked_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL",
    [userId]
  );
}

async function purgeExpiredRefreshTokens() {
  await pool.query("DELETE FROM refresh_tokens WHERE expires_at < NOW() OR revoked_at IS NOT NULL");
}

async function deleteAllUsers() {
  await pool.query("TRUNCATE TABLE refresh_tokens RESTART IDENTITY CASCADE");
  await pool.query("TRUNCATE TABLE rag_solve_jobs RESTART IDENTITY CASCADE");
  await pool.query("TRUNCATE TABLE quiz_attempt_answers RESTART IDENTITY CASCADE");
  await pool.query("TRUNCATE TABLE quiz_attempts RESTART IDENTITY CASCADE");
  await pool.query("TRUNCATE TABLE users RESTART IDENTITY CASCADE");
}

async function createRagSolveJob({ userId, questionText, options, wrongChoice, answerChoice, requestPayload }) {
  const safeOptions = Array.isArray(options) ? options.slice(0, 4).map(x => String(x || "").trim()) : [];
  if (safeOptions.length !== 4 || safeOptions.some(x => !x)) {
    throw new Error("invalid_options");
  }

  const result = await pool.query(
    `INSERT INTO rag_solve_jobs (
       user_id, question_text, option_1, option_2, option_3, option_4,
       wrong_choice, answer_choice, request_payload
     )
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
     RETURNING id, status, created_at AS "createdAt"`,
    [
      userId,
      String(questionText || "").trim(),
      safeOptions[0],
      safeOptions[1],
      safeOptions[2],
      safeOptions[3],
      wrongChoice ? String(wrongChoice).trim() : null,
      answerChoice ? String(answerChoice).trim() : null,
      JSON.stringify(requestPayload || {})
    ]
  );

  return result.rows[0];
}

async function getRagSolveJobById(jobId) {
  const result = await pool.query(
    `SELECT id, user_id AS "userId", status, question_text AS "questionText",
            option_1 AS "option1", option_2 AS "option2", option_3 AS "option3", option_4 AS "option4",
            wrong_choice AS "wrongChoice", answer_choice AS "answerChoice",
            request_payload AS "requestPayload", result_payload AS "resultPayload",
            error_message AS "errorMessage", created_at AS "createdAt",
            started_at AS "startedAt", completed_at AS "completedAt"
     FROM rag_solve_jobs
     WHERE id = $1
     LIMIT 1`,
    [jobId]
  );

  return result.rows[0] || null;
}

async function markRagSolveJobProcessing(jobId) {
  const result = await pool.query(
    `UPDATE rag_solve_jobs
     SET status = 'processing', started_at = NOW(), error_message = NULL
     WHERE id = $1
     RETURNING id`,
    [jobId]
  );

  return result.rows[0] || null;
}

async function completeRagSolveJob(jobId, resultPayload) {
  const result = await pool.query(
    `UPDATE rag_solve_jobs
     SET status = 'completed', result_payload = $2::jsonb, error_message = NULL, completed_at = NOW()
     WHERE id = $1
     RETURNING id`,
    [jobId, JSON.stringify(resultPayload || {})]
  );

  return result.rows[0] || null;
}

async function failRagSolveJob(jobId, errorMessage) {
  const result = await pool.query(
    `UPDATE rag_solve_jobs
     SET status = 'failed', error_message = $2, completed_at = NOW()
     WHERE id = $1
     RETURNING id`,
    [jobId, String(errorMessage || "unknown_error")]
  );

  return result.rows[0] || null;
}

async function getRagSolveHistoryByUser(userId, limit = 100) {
  const safeLimit = Math.min(Math.max(Number(limit) || 50, 1), 300);
  const result = await pool.query(
    `SELECT id, status, question_text AS "questionText",
            option_1 AS "option1", option_2 AS "option2", option_3 AS "option3", option_4 AS "option4",
            wrong_choice AS "wrongChoice", answer_choice AS "answerChoice",
            error_message AS "errorMessage", created_at AS "createdAt",
            started_at AS "startedAt", completed_at AS "completedAt",
            result_payload AS "resultPayload"
     FROM rag_solve_jobs
     WHERE user_id = $1
     ORDER BY created_at DESC
     LIMIT $2`,
    [userId, safeLimit]
  );

  return result.rows;
}

async function getRagSolveJobDetail(userId, jobId) {
  const result = await pool.query(
    `SELECT id, status, question_text AS "questionText",
            option_1 AS "option1", option_2 AS "option2", option_3 AS "option3", option_4 AS "option4",
            wrong_choice AS "wrongChoice", answer_choice AS "answerChoice",
            request_payload AS "requestPayload", result_payload AS "resultPayload",
            error_message AS "errorMessage", created_at AS "createdAt",
            started_at AS "startedAt", completed_at AS "completedAt"
     FROM rag_solve_jobs
     WHERE user_id = $1 AND id = $2
     LIMIT 1`,
    [userId, jobId]
  );

  return result.rows[0] || null;
}

async function saveQuizAttempt({ userId, quizUid, totalQuestions, correctCount, score, durationSec, answers }) {
  const client = await pool.connect();

  try {
    await client.query("BEGIN");

    const attemptResult = await client.query(
      `INSERT INTO quiz_attempts (user_id, quiz_uid, total_questions, correct_count, score, duration_sec)
       VALUES ($1, $2, $3, $4, $5, $6)
       RETURNING id, created_at`,
      [userId, quizUid || null, totalQuestions, correctCount, score, durationSec]
    );

    const attemptId = attemptResult.rows[0].id;

    for (const item of answers) {
      await client.query(
        `INSERT INTO quiz_attempt_answers
          (attempt_id, question_id, subject, question_text, selected_index, correct_index, is_correct)
         VALUES ($1, $2, $3, $4, $5, $6, $7)`,
        [
          attemptId,
          item.questionId,
          item.subject,
          item.questionText,
          item.selectedIndex,
          item.correctIndex,
          item.isCorrect
        ]
      );
    }

    await client.query("COMMIT");
    return { id: attemptId, createdAt: attemptResult.rows[0].created_at };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

async function getQuizHistoryByUser(userId, limit = 100) {
  const safeLimit = Math.min(Math.max(Number(limit) || 50, 1), 500);

  const result = await pool.query(
    `SELECT id, quiz_uid AS "quizUid", total_questions AS "totalQuestions", correct_count AS "correctCount",
            score, duration_sec AS "durationSec", created_at AS "createdAt"
     FROM quiz_attempts
     WHERE user_id = $1
     ORDER BY created_at DESC
     LIMIT $2`,
    [userId, safeLimit]
  );

  return result.rows;
}

async function getQuizAttemptDetail(userId, attemptId) {
  const attemptResult = await pool.query(
    `SELECT id, quiz_uid AS "quizUid", total_questions AS "totalQuestions", correct_count AS "correctCount",
            score, duration_sec AS "durationSec", created_at AS "createdAt"
     FROM quiz_attempts
     WHERE id = $1 AND user_id = $2`,
    [attemptId, userId]
  );

  const attempt = attemptResult.rows[0];
  if (!attempt) {
    return null;
  }

  const answersResult = await pool.query(
    `SELECT question_id AS "questionId", subject, question_text AS "questionText",
            selected_index AS "selectedIndex", correct_index AS "correctIndex", is_correct AS "isCorrect"
     FROM quiz_attempt_answers
     WHERE attempt_id = $1
     ORDER BY id ASC`,
    [attemptId]
  );

  return {
    ...attempt,
    answers: answersResult.rows
  };
}

module.exports = {
  DATABASE_URL,
  initDatabase,
  createUser,
  findUserById,
  findUserByUsername,
  findUserByEmail,
  verifyUser,
  verifyUserPasswordById,
  issueOrGetApiTokenByUserId,
  findUserByApiToken,
  storeRefreshToken,
  findRefreshToken,
  revokeRefreshToken,
  revokeAllRefreshTokensByUser,
  purgeExpiredRefreshTokens,
  deleteAllUsers,
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
};
