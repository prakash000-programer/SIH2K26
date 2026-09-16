import React from 'react';

interface FootfallCardProps {
  countIn: number;
  countOut: number;
  footfallRatePerMin: number;
  isHighDensity?: boolean;
}

export const FootfallCard: React.FC<FootfallCardProps> = ({
  countIn,
  countOut,
  footfallRatePerMin,
  isHighDensity = false,
}) => {
  const currentOccupancy = Math.max(0, countIn - countOut);

  return (
    <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ fontSize: '1.15rem' }}>Store Traffic & Footfall</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Real-time directional entry/exit tracking
          </p>
        </div>
        {isHighDensity ? (
          <span
            className="chip-tag"
            style={{
              background: 'rgba(239, 68, 68, 0.2)',
              borderColor: 'rgba(239, 68, 68, 0.5)',
              color: 'var(--accent-rose)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-rose)' }} />
            High Crowd Density
          </span>
        ) : (
          <span
            className="chip-tag"
            style={{
              background: 'rgba(16, 185, 129, 0.15)',
              borderColor: 'rgba(16, 185, 129, 0.4)',
              color: 'var(--accent-emerald)',
            }}
          >
            Normal Flow
          </span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
        {/* Net Occupancy */}
        <div
          style={{
            background: 'rgba(7, 10, 19, 0.6)',
            borderRadius: '12px',
            padding: '1.25rem',
            border: '1px solid var(--border-subtle)',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Current In Store
          </div>
          <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--accent-cyan)', marginTop: '0.25rem' }}>
            {currentOccupancy}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
            Active Shoppers
          </div>
        </div>

        {/* Total IN */}
        <div
          style={{
            background: 'rgba(7, 10, 19, 0.6)',
            borderRadius: '12px',
            padding: '1.25rem',
            border: '1px solid var(--border-subtle)',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Total Entries (IN)
          </div>
          <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--accent-emerald)', marginTop: '0.25rem' }}>
            ↑ {countIn}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
            Directional Crossed
          </div>
        </div>

        {/* Total OUT */}
        <div
          style={{
            background: 'rgba(7, 10, 19, 0.6)',
            borderRadius: '12px',
            padding: '1.25rem',
            border: '1px solid var(--border-subtle)',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Total Exits (OUT)
          </div>
          <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--accent-amber)', marginTop: '0.25rem' }}>
            ↓ {countOut}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
            Checkouts Completed
          </div>
        </div>
      </div>

      {/* Arrival velocity bar */}
      <div
        style={{
          background: 'rgba(7, 10, 19, 0.4)',
          borderRadius: '8px',
          padding: '0.85rem 1rem',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span style={{ fontSize: '1.2rem' }}>⚡</span>
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Arrival Velocity</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Smoothed arrival rate over last 5-min window</div>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#ffffff' }}>
            {footfallRatePerMin.toFixed(1)} <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>shoppers/min</span>
          </div>
        </div>
      </div>
    </div>
  );
};
