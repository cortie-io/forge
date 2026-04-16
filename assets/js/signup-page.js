const form = document.getElementById('signup-form');
const msg = document.getElementById('signup-msg');
const btn = document.getElementById('signup-btn');

function setMsg(type, text) {
  msg.className = `msg ${type || ''}`;
  msg.textContent = text || '';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const payload = {
    username: document.getElementById('username').value.trim().toLowerCase(),
    name: document.getElementById('name').value.trim(),
    studentNumber: document.getElementById('student-number').value.trim(),
    email: document.getElementById('email').value.trim().toLowerCase(),
    password: document.getElementById('password').value
  };

  if (!payload.username || !payload.name || !payload.studentNumber || !payload.email || !payload.password) {
    setMsg('err', '모든 항목을 입력해주세요.');
    return;
  }

  btn.disabled = true;
  setMsg('', '');
  try {
    const r = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.message || '회원가입에 실패했습니다.');
    setMsg('ok', '회원가입 완료! 로그인 페이지로 이동합니다.');
    setTimeout(() => { location.href = '/pages/login.html'; }, 900);
  } catch (err) {
    setMsg('err', err.message);
  } finally {
    btn.disabled = false;
  }
});
