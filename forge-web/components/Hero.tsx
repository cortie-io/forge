"use client";
import { useRouter } from "next/navigation";

export function Hero() {
  const router = useRouter();
  return (
    <section className="hero" style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '140px 48px 80px', textAlign: 'center', position: 'relative', overflow: 'hidden',
    }}>
      <div className="hero-grid" style={{position: 'absolute', inset: 0, zIndex: 0, backgroundImage: 'linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)', backgroundSize: '64px 64px', maskImage: 'radial-gradient(ellipse 80% 60% at 50% 0%, black 40%, transparent 100%)'}} />
      <div className="hero-glow-1" style={{position: 'absolute', width: 800, height: 500, top: -100, left: '50%', transform: 'translateX(-50%)', background: 'radial-gradient(ellipse, rgba(255,99,99,0.08) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0}} />
      <div className="hero-glow-2" style={{position: 'absolute', width: 400, height: 300, top: '20%', left: '20%', background: 'radial-gradient(ellipse, rgba(85,179,255,0.04) 0%, transparent 70%)', pointerEvents: 'none', zIndex: 0}} />
      <div className="hero-glow-3" style={{position: 'absolute', width: 300, height: 200, top: '30%', right: '15%', background: 'radial-gradient(ellipse, rgba(95,201,146,0.04) 0%, transparent 70%)', pointerEvents: 'none', zIndex: 0}} />

      <div className="hero-content" style={{position: 'relative', zIndex: 1, maxWidth: 760}}>
        <div className="hero-eyebrow" style={{display: 'inline-flex', alignItems: 'center', gap: 8, background: 'var(--surface)', border: '1px solid var(--border-mid)', borderRadius: 100, padding: '6px 16px 6px 10px', marginBottom: 32, boxShadow: 'var(--shadow-card)'}}>
          <span className="eyebrow-badge" style={{background: 'var(--red)', color: 'white', borderRadius: 100, padding: '2px 9px', fontSize: 11, fontWeight: 700, letterSpacing: 0.5}}>NEW</span>
          <span className="eyebrow-text" style={{fontSize: 13, fontWeight: 500, color: 'var(--text-3)', letterSpacing: 0.2}}>Claude AI-powered certification learning platform</span>
        </div>
        <h1 style={{fontSize: 'clamp(44px, 6.5vw, 72px)', fontWeight: 600, lineHeight: 1.08, letterSpacing: '-0.025em', color: 'var(--text)', marginBottom: 24, fontFeatureSettings: '"kern","ss02","ss08"'}}>
          How to <em style={{fontStyle: 'normal', background: 'linear-gradient(135deg, var(--red) 0%, #ff8f8f 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text'}}>train</em><br />for certification success
        </h1>
        <p className="hero-sub" style={{fontSize: 18, fontWeight: 400, color: 'var(--text-3)', lineHeight: 1.7, letterSpacing: 0.15, maxWidth: 520, margin: '0 auto 40px'}}>
          Your AI tutor explains concepts 24/7, analyzes wrong answers, and targets weak spots so you can pass through understanding, not memorization.
        </p>
        <div className="hero-actions" style={{display: 'flex', gap: 12, justifyContent: 'center', marginBottom: 56}}>
          <button className="btn-primary" style={{display: 'inline-flex', alignItems: 'center', gap: 8, background: 'var(--red)', color: 'white', border: 'none', borderRadius: 10, padding: '13px 28px', fontSize: 15, fontWeight: 600, cursor: 'pointer', fontFamily: 'var(--font)', letterSpacing: 0.1, transition: 'all 0.15s', boxShadow: '0 0 28px rgba(255,99,99,0.35), 0 4px 12px rgba(255,99,99,0.2), var(--shadow-btn)'}} onClick={() => router.push("/chat") }>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="white"><path d="M13 2L4.09 12.97 12 12.45 11 22l8.91-10.97L12 11.55 13 2z"/></svg>
            Start Free Now
          </button>
          <button className="btn-secondary" style={{display: 'inline-flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.04)', color: 'var(--text-2)', border: '1px solid var(--border-mid)', borderRadius: 10, padding: '13px 24px', fontSize: 15, fontWeight: 500, cursor: 'pointer', fontFamily: 'var(--font)', letterSpacing: 0.1, transition: 'all 0.15s', boxShadow: 'var(--shadow-btn)'}}>Try Demo</button>
        </div>
      </div>
    </section>
  );
}
