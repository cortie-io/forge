export function StatsBar() {
  return (
    <div className="stats-bar" style={{maxWidth: 900, margin: '0 auto', padding: '0 48px 80px'}}>
      <div className="stats-inner" style={{background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: '32px 48px', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0, boxShadow: 'var(--shadow-card)', position: 'relative', overflow: 'hidden'}}>
        <div style={{content: '', position: 'absolute', top: 0, left: 0, right: 0, height: 1, background: 'linear-gradient(90deg, transparent, rgba(255,99,99,0.3), transparent)'}} />
        <div className="stat-item" style={{textAlign: 'center', padding: '0 24px', borderRight: '1px solid var(--border)'}}>
          <div className="stat-num" style={{fontSize: 32, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.03em', lineHeight: 1, marginBottom: 6}}>
            12<span style={{color: 'var(--red)'}}>,4</span>00<span style={{color: 'var(--red)'}}>+</span>
          </div>
          <div className="stat-label" style={{fontSize: 13, color: 'var(--text-4)', fontWeight: 500, letterSpacing: '0.2px'}}>Successful Learners</div>
        </div>
        <div className="stat-item" style={{textAlign: 'center', padding: '0 24px', borderRight: '1px solid var(--border)'}}>
          <div className="stat-num" style={{fontSize: 32, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.03em', lineHeight: 1, marginBottom: 6}}>
            58<span style={{color: 'var(--red)'}}>+</span>
          </div>
          <div className="stat-label" style={{fontSize: 13, color: 'var(--text-4)', fontWeight: 500, letterSpacing: '0.2px'}}>Certifications Supported</div>
        </div>
        <div className="stat-item" style={{textAlign: 'center', padding: '0 24px', borderRight: '1px solid var(--border)'}}>
          <div className="stat-num" style={{fontSize: 32, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.03em', lineHeight: 1, marginBottom: 6}}>
            2.1<span style={{color: 'var(--red)'}}>M+</span>
          </div>
          <div className="stat-label" style={{fontSize: 13, color: 'var(--text-4)', fontWeight: 500, letterSpacing: '0.2px'}}>Questions Solved</div>
        </div>
        <div className="stat-item" style={{textAlign: 'center', padding: '0 24px'}}>
          <div className="stat-num" style={{fontSize: 32, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.03em', lineHeight: 1, marginBottom: 6}}>
            94<span style={{color: 'var(--red)'}}>%</span>
          </div>
          <div className="stat-label" style={{fontSize: 13, color: 'var(--text-4)', fontWeight: 500, letterSpacing: '0.2px'}}>Goal Achievement Rate</div>
        </div>
      </div>
    </div>
  );
}
