import React, { useState } from 'react';
import type { AlertItem } from '../types';
import { api } from '../api/client';

interface StaffViewProps {
  alerts: AlertItem[];
  onDismissAlert: (id: string) => void;
  queueSizes: Record<string, number>;
  onQueueChange?: () => void;
}

export const StaffView: React.FC<StaffViewProps> = ({
  alerts,
  onDismissAlert,
  queueSizes,
  onQueueChange,
}) => {
  const [actingOn, setActingOn] = useState<string | null>(null);

  const handleIncrement = async (counterId: string) => {
    try {
      await api.incrementQueue(counterId);
      onQueueChange?.();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDecrement = async (counterId: string) => {
    try {
      await api.decrementQueue(counterId);
      onQueueChange?.();
    } catch (err) {
      console.error(err);
    }
  };

  const handleAction = async (alertId: string, _actionName: string) => {
    setActingOn(alertId);
    setTimeout(() => {
      setActingOn(null);
      onDismissAlert(alertId);
    }, 600);
  };

  // Demo alert if feed is empty
  const activeAlerts = alerts.length > 0 ? alerts : [
    {
      id: 'demo-1',
      type: 'queue' as const,
      title: 'Action Recommended: Open Counter 2',
      message: 'Checkout demand surge detected. 8 shoppers currently in shopping zone expected to queue within 3 minutes.',
      timestamp: Date.now() - 60000,
    },
    {
      id: 'demo-2',
      type: 'stockout' as const,
      title: 'Restock Alert: Slot A - Soft Drinks',
      message: 'Shelf sensor verified 3 consecutive empty readings. Estimated 0 units on display.',
      timestamp: Date.now() - 180000,
    },
  ];

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="view-header">
        <div className="view-title-group">
          <h2>Floor Staff Action Feed</h2>
          <div className="view-subtitle">
            Immediate real-time alerts for checkout queue surges, shelf stock-outs, and customer hotspots
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span className="chip-tag" style={{ background: 'rgba(244, 63, 94, 0.15)', borderColor: 'rgba(244, 63, 94, 0.4)', color: 'var(--accent-rose)' }}>
            {activeAlerts.length} Active Notice{activeAlerts.length === 1 ? '' : 's'}
          </span>
        </div>
      </div>

      {/* Quick Counter Control Bar for Floor Staff */}
      <div className="glass-panel" style={{ padding: '1.25rem 1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <h4 style={{ fontSize: '1rem' }}>Quick Counter Queue Status</h4>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Direct sensor simulation or manual floor staff queue adjustment
            </p>
          </div>
          <span className="chip-tag">Sensor Sync Active</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          {['counter_1', 'counter_2', 'counter_3'].map((cid, idx) => {
            const size = queueSizes[cid] || 0;
            const isHigh = size >= 4;
            return (
              <div
                key={cid}
                style={{
                  background: 'rgba(7, 10, 19, 0.7)',
                  borderRadius: '10px',
                  padding: '1rem',
                  border: isHigh ? '1px solid var(--accent-rose)' : '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Counter #{idx + 1}
                  </div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: isHigh ? 'var(--accent-rose)' : 'white' }}>
                    {size} <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 400 }}>waiting</span>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '0.4rem' }}>
                  <button
                    onClick={() => handleDecrement(cid)}
                    className="btn-secondary"
                    style={{ padding: '6px 12px', fontSize: '1rem' }}
                    title="Someone served / left"
                  >
                    -
                  </button>
                  <button
                    onClick={() => handleIncrement(cid)}
                    className="btn-primary"
                    style={{ padding: '6px 12px', fontSize: '1rem' }}
                    title="Someone joined queue"
                  >
                    +
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Alert Feed Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h4 style={{ fontSize: '1.05rem', color: 'var(--text-primary)' }}>Live Action Queue</h4>
        {activeAlerts.map((alert) => {
          const isQueue = alert.type === 'queue';
          const isStockout = alert.type === 'stockout';

          return (
            <div
              key={alert.id}
              className={`alert-card ${alert.type}`}
              style={{
                opacity: actingOn === alert.id ? 0.4 : 1,
                transform: actingOn === alert.id ? 'scale(0.98)' : 'none',
              }}
            >
              <div style={{ fontSize: '1.8rem', lineHeight: 1 }}>
                {isQueue ? '⚡' : isStockout ? '📦' : '👥'}
              </div>

              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem' }}>
                  <span
                    className="alert-badge"
                    style={{
                      background: isQueue
                        ? 'rgba(245, 158, 11, 0.2)'
                        : isStockout
                        ? 'rgba(244, 63, 94, 0.2)'
                        : 'rgba(99, 102, 241, 0.2)',
                      color: isQueue
                        ? 'var(--accent-amber)'
                        : isStockout
                        ? 'var(--accent-rose)'
                        : 'var(--accent-indigo)',
                    }}
                  >
                    {alert.type.toUpperCase()}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </span>
                </div>

                <div style={{ fontSize: '1rem', fontWeight: 700, color: '#ffffff' }}>
                  {alert.title}
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                  {alert.message}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', alignSelf: 'center' }}>
                {isQueue && (
                  <button
                    onClick={() => handleAction(alert.id, 'opened_counter')}
                    className="btn-primary"
                    style={{ padding: '0.5rem 1rem', fontSize: '0.8rem' }}
                  >
                    Open Counter
                  </button>
                )}

                {isStockout && (
                  <button
                    onClick={() => handleAction(alert.id, 'restocked')}
                    className="btn-primary"
                    style={{
                      padding: '0.5rem 1rem',
                      fontSize: '0.8rem',
                      background: 'linear-gradient(135deg, var(--accent-emerald), #059669)',
                    }}
                  >
                    Restock Done
                  </button>
                )}

                <button
                  onClick={() => onDismissAlert(alert.id)}
                  className="btn-secondary"
                  style={{ padding: '0.5rem 0.85rem', fontSize: '0.8rem' }}
                >
                  Dismiss
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
