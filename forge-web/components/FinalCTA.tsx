"use client";
import { useRouter } from "next/navigation";

export function FinalCTA() {
  const router = useRouter();
  return (
    <div style={{maxWidth: 1160, margin: '0 auto'}}>
      <div className="cta-section" style={{margin: '0 48px 80px', borderRadius: 24, background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-card)', overflow: 'hidden', position: 'relative', padding: '80px 64px', textAlign: 'center'}}>
        <h2 style={{fontSize: 'clamp(28px, 4vw, 48px)', fontWeight: 600, color: 'var(--text)', letterSpacing: '-0.02em', lineHeight: 1.15, marginBottom: 16, position: 'relative'}}>Start preparing to pass<br />today</h2>
        <p style={{fontSize: 16, color: 'var(--text-3)', marginBottom: 36, position: 'relative'}}>First 7 days are free. No credit card required.</p>
        <div className="cta-actions" style={{display: 'flex', gap: 12, justifyContent: 'center', position: 'relative'}}>
          <button className="btn-primary" style={{display: 'inline-flex', alignItems: 'center', gap: 8, background: 'var(--red)', color: 'white', border: 'none', borderRadius: 10, padding: '13px 28px', fontSize: 15, fontWeight: 600, cursor: 'pointer', fontFamily: 'var(--font)', letterSpacing: 0.1, transition: 'all 0.15s', boxShadow: '0 0 28px rgba(255,99,99,0.35), 0 4px 12px rgba(255,99,99,0.2), var(--shadow-btn)'}} onClick={() => router.push("/chat") }>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="white"><path d="M13 2L4.09 12.97 12 12.45 11 22l8.91-10.97L12 11.55 13 2z"/></svg>
            Start Free
          </button>
          <button className="btn-secondary" style={{display: 'inline-flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.04)', color: 'var(--text-2)', border: '1px solid var(--border-mid)', borderRadius: 10, padding: '13px 24px', fontSize: 15, fontWeight: 500, cursor: 'pointer', fontFamily: 'var(--font)', letterSpacing: 0.1, transition: 'all 0.15s', boxShadow: 'var(--shadow-btn)'}}>Contact Sales</button>
        </div>
      </div>
    </div>
  );
}
