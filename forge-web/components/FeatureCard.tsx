interface FeatureCardProps {
  title: string;
  description: string;
}

export function FeatureCard({ title, description }: FeatureCardProps) {
  return (
    <div style={{
      background: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-card)',
      boxShadow: 'var(--shadow-card)',
      padding: 32,
      minWidth: 340,
      maxWidth: 400,
      color: 'var(--color-text)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'flex-start',
      gap: 12,
    }}>
      <h2 style={{ fontSize: 22, fontWeight: 400, margin: 0 }}>{title}</h2>
      <p style={{ color: 'var(--color-secondary)', fontSize: 16, fontWeight: 500, margin: 0 }}>{description}</p>
    </div>
  );
}
