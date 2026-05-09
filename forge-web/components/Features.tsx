export function Features() {
  return (
    <section className="section" id="features" style={{padding: '80px 48px', maxWidth: 1160, margin: '0 auto'}}>
      <div className="section-header" style={{marginBottom: 56}}>
        <div className="section-kicker" style={{display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 11, fontWeight: 700, color: 'var(--red)', letterSpacing: '1.4px', textTransform: 'uppercase', marginBottom: 16}}>
          <span style={{display: 'inline-block', width: 16, height: 1, background: 'var(--red)'}}></span>
          Core Features
        </div>
        <h2 className="section-title" style={{fontSize: 'clamp(28px, 3.5vw, 44px)', fontWeight: 500, color: 'var(--text)', lineHeight: 1.18, letterSpacing: '-0.015em', maxWidth: 540}}>
          Only what you need<br />to <em style={{fontStyle: 'normal', color: 'var(--red)'}}>pass</em>
        </h2>
        <p className="section-desc" style={{fontSize: 16, color: 'var(--text-3)', lineHeight: 1.7, maxWidth: 480, marginTop: 14}}>
          Not just another quiz app. AI analyzes your learning pattern and designs the fastest route to passing.
        </p>
      </div>
      <div className="features-grid" style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1, background: 'var(--border)', borderRadius: 20, overflow: 'hidden', boxShadow: 'var(--shadow-card)'}}>
        {/* Large card (2-column) */}
        <div className="feature-card feature-card-large" style={{gridColumn: 'span 2', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32, background: 'var(--surface)', padding: '36px 32px', position: 'relative', overflow: 'hidden', transition: 'background 0.2s'}}>
          <div>
            <div className="feature-icon-wrap fi-red" style={{width: 44, height: 44, borderRadius: 12, border: '1px solid rgba(255,99,99,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20, background: 'rgba(255,99,99,0.08)'}}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FF6363" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/><path d="M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M5.64 18.36l2.12-2.12M16.24 7.76l2.12-2.12"/></svg>
            </div>
            <h3 style={{fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 10, letterSpacing: '-0.01em'}}>AI Weakness Diagnosis</h3>
            <p style={{fontSize: 14, color: 'var(--text-3)', lineHeight: 1.7, letterSpacing: 0.1}}>
              It reviews your solve history to detect missing concepts automatically, so you focus on score-critical topics instead of studying everything blindly.
            </p>
          </div>
          <div>
            <div className="feature-icon-wrap fi-blue" style={{width: 44, height: 44, borderRadius: 12, border: '1px solid rgba(85,179,255,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20, background: 'rgba(85,179,255,0.08)'}}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#55b3ff" strokeWidth="2" strokeLinecap="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            </div>
            <h3 style={{fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 10, letterSpacing: '-0.01em'}}>24/7 AI Tutor Q&A</h3>
            <p style={{fontSize: 14, color: 'var(--text-3)', lineHeight: 1.7, letterSpacing: 0.1}}>
              Ask whenever something from your materials is unclear. It explains concepts simply and helps repetition with examples.
            </p>
          </div>
        </div>
        {/* 3 normal cards */}
        <div className="feature-card" style={{background: 'var(--surface)', padding: '36px 32px', position: 'relative', overflow: 'hidden', transition: 'background 0.2s'}}>
          <div className="feature-icon-wrap fi-green" style={{width: 44, height: 44, borderRadius: 12, border: '1px solid rgba(95,201,146,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20, background: 'rgba(95,201,146,0.08)'}}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#5fc992" strokeWidth="2" strokeLinecap="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
          </div>
          <h3 style={{fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 10, letterSpacing: '-0.01em'}}>Exam-Style Mock Tests</h3>
          <p style={{fontSize: 14, color: 'var(--text-3)', lineHeight: 1.7, letterSpacing: 0.1}}>
            Practice with real exam patterns and difficulty. Get instant explanations and root-cause analysis for mistakes.
          </p>
          <div className="card-dots" style={{position: 'absolute', bottom: 20, right: 20, width: 80, height: 60, opacity: 0.25, backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.4) 1px, transparent 1px)', backgroundSize: '10px 10px'}}></div>
        </div>
        <div className="feature-card" style={{background: 'var(--surface)', padding: '36px 32px', position: 'relative', overflow: 'hidden', transition: 'background 0.2s'}}>
          <div className="feature-icon-wrap fi-yellow" style={{width: 44, height: 44, borderRadius: 12, border: '1px solid rgba(255,188,51,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20, background: 'rgba(255,188,51,0.08)'}}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ffbc33" strokeWidth="2" strokeLinecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          </div>
          <h3 style={{fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 10, letterSpacing: '-0.01em'}}>Progress Tracking</h3>
          <p style={{fontSize: 14, color: 'var(--text-3)', lineHeight: 1.7, letterSpacing: 0.1}}>
            Visualize accuracy, study time, and error patterns by topic. The plan auto-adjusts to your target date.
          </p>
          <div className="card-dots" style={{position: 'absolute', bottom: 20, right: 20, width: 80, height: 60, opacity: 0.25, backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.4) 1px, transparent 1px)', backgroundSize: '10px 10px'}}></div>
        </div>
        <div className="feature-card" style={{background: 'var(--surface)', padding: '36px 32px', position: 'relative', overflow: 'hidden', transition: 'background 0.2s'}}>
          <div className="feature-icon-wrap fi-red" style={{width: 44, height: 44, borderRadius: 12, border: '1px solid rgba(255,99,99,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20, background: 'rgba(255,99,99,0.08)'}}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FF6363" strokeWidth="2" strokeLinecap="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
          </div>
          <h3 style={{fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 10, letterSpacing: '-0.01em'}}>Deep Concept Explanations</h3>
          <p style={{fontSize: 14, color: 'var(--text-3)', lineHeight: 1.7, letterSpacing: 0.1}}>
            Go beyond memorization. Learn principles and real-world use cases for longer retention.
          </p>
        </div>
        <div className="feature-card" style={{background: 'var(--surface)', padding: '36px 32px', position: 'relative', overflow: 'hidden', transition: 'background 0.2s'}}>
          <div className="feature-icon-wrap fi-blue" style={{width: 44, height: 44, borderRadius: 12, border: '1px solid rgba(85,179,255,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20, background: 'rgba(85,179,255,0.08)'}}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#55b3ff" strokeWidth="2" strokeLinecap="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
          </div>
          <h3 style={{fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 10, letterSpacing: '-0.01em'}}>Streak & Goal Management</h3>
          <p style={{fontSize: 14, color: 'var(--text-3)', lineHeight: 1.7, letterSpacing: 0.1}}>
            Build consistency with daily streaks. Set a target date and get automatically distributed daily workload.
          </p>
        </div>
      </div>
    </section>
  );
}
