import { Nav } from '../components/Nav';
import { Hero } from '../components/Hero';
import { Steps } from '../components/Steps';
import { Features } from '../components/Features';
import { StatsBar } from '../components/StatsBar';
import { Footer } from '../components/Footer';
import { CertGrid } from '../components/CertGrid';
import { Testimonial } from '../components/Testimonial';
import { FinalCTA } from '../components/FinalCTA';

export default function Home() {
  return (
    <>
      <Nav />
      <main style={{ minHeight: '100vh', background: 'var(--bg)' }}>
        <Hero />
        <StatsBar />
        <Features />
        <Steps />
        <CertGrid />
        <Testimonial />
        <FinalCTA />
      </main>
      <Footer />
    </>
  );
}
