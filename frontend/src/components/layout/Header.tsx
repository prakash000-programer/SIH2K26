import React from 'react';
import { useAuth } from '../../context/AuthContext';
import type { UserRole } from '../../types';

interface HeaderProps {
  wsConnected: boolean;
  alertCount: number;
}

export const Header: React.FC<HeaderProps> = ({ wsConnected, alertCount }) => {
  const { role, setRole } = useAuth();

  const roles: { id: UserRole; label: string; icon: string }[] = [
    { id: 'manager', label: 'Store Manager', icon: '🏢' },
    { id: 'camera', label: 'Live Camera', icon: '🎥' },
    { id: 'staff', label: 'Floor Staff', icon: '🚨' },
    { id: 'owner', label: 'Executive ROI', icon: '💼' },
    { id: 'queue', label: 'Queue Intel', icon: '⏱️' },
    { id: 'inventory', label: 'Shelf Stock', icon: '📦' },
    { id: 'calibration', label: 'Calibration', icon: '📐' },
  ];

  return (
    <header className="header-container">
      <div className="brand-badge">
        <div className="brand-icon">⚡</div>
        <div>
          <div className="brand-name">
            IntelliSales
            <span className="chip-tag">Edge AI</span>
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <span>Privacy-First</span>
            <span>•</span>
            <span>Zero Video Storage</span>
            <span>•</span>
            <span style={{ color: 'var(--accent-cyan)' }}>Qualcomm QCS6490 Ready</span>
          </div>
        </div>
      </div>

      <nav className="nav-roles">
        {roles.map((r) => {
          const isActive = role === r.id;
          const showBadge = r.id === 'staff' && alertCount > 0;
          return (
            <button
              key={r.id}
              onClick={() => setRole(r.id)}
              className={`role-tab-btn ${isActive ? 'active' : ''}`}
              title={`Switch to ${r.label}`}
            >
              <span>{r.icon}</span>
              <span>{r.label}</span>
              {showBadge && (
                <span
                  style={{
                    background: 'var(--accent-rose)',
                    color: 'white',
                    fontSize: '0.65rem',
                    padding: '1px 6px',
                    borderRadius: '10px',
                    fontWeight: 700,
                  }}
                >
                  {alertCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div className={`pulse-indicator ${wsConnected ? 'live' : ''}`} style={{
          background: wsConnected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          color: wsConnected ? 'var(--accent-emerald)' : 'var(--accent-rose)',
          border: `1px solid ${wsConnected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
        }}>
          <div
            className="pulse-dot"
            style={{
              background: wsConnected ? 'var(--accent-emerald)' : 'var(--accent-rose)',
              boxShadow: `0 0 10px ${wsConnected ? 'var(--accent-emerald)' : 'var(--accent-rose)'}`,
            }}
          />
          <span>{wsConnected ? 'Edge Live Stream' : 'Connecting...'}</span>
        </div>
      </div>
    </header>
  );
};
