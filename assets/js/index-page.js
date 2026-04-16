const navActions = document.getElementById('nav-actions');
const heroDemoBtn = document.getElementById('hero-demo-btn');
const heroStartBtn = document.getElementById('hero-start-btn');
const ctaStartBtn = document.getElementById('cta-start-btn');

async function doLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
  } catch (e) {
    // Ignore and still reload to clear UI state.
  }
  location.reload();
}

(async () => {
  try {
    const r = await fetch('/api/auth/me', { credentials: 'same-origin' });
    if (!r.ok) return;
    const d = await r.json();
    const user = d.user?.name || d.user?.username || '학습자';
    navActions.innerHTML = `
      <span style="font-size:13px;color:var(--t2);font-weight:600;">${user}</span>
      <button class="btn ghost sm" id="logout-btn">로그아웃</button>
      <button class="btn primary sm" id="go-quiz-btn">학습하기</button>
    `;
    document.getElementById('logout-btn').onclick = doLogout;
    document.getElementById('go-quiz-btn').onclick = () => { location.href = '/pages/dashboard.html'; };
    heroDemoBtn.style.display = 'inline-flex';
    heroStartBtn.style.display = 'none';
  } catch (e) {
    // Keep anonymous UI.
  }
})();

heroStartBtn.onclick = () => { location.href = '/pages/signup.html'; };
ctaStartBtn.onclick = () => { location.href = '/pages/signup.html'; };
heroDemoBtn.onclick = () => { location.href = '/pages/dashboard.html'; };
