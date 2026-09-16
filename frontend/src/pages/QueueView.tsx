import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { QueuePrediction, QueueConfig } from '../types';

interface QueueViewProps {
  queueSizes: Record<string, number>;
  onQueueChange?: () => void;
}

export const QueueView: React.FC<QueueViewProps> = ({ queueSizes, onQueueChange }) => {
  const [prediction, setPrediction] = useState<QueuePrediction | null>(null);
  const [config, setConfig] = useState<QueueConfig>({
    avg_service_time_s: 45,
    conversion_rate: 0.3,
    max_acceptable_wait_time_s: 180,
    avg_shopping_time_s: 300,
    smoothing_alpha: 0.3,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const fetchPrediction = useCallback(async () => {
    try {
      const pred = await api.getQueuePrediction();
      setPrediction(pred);
    } catch (err) {
      console.error('Failed to get queue prediction:', err);
    }
  }, []);

  useEffect(() => {
    fetchPrediction();
    const interval = setInterval(fetchPrediction, 5000);
    return () => clearInterval(interval);
  }, [fetchPrediction]);

  const handleIncrement = async (counterId: string) => {
    try {
      await api.incrementQueue(counterId);
      onQueueChange?.();
      fetchPrediction();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDecrement = async (counterId: string) => {
    try {
      await api.decrementQueue(counterId);
      onQueueChange?.();
      fetchPrediction();
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await api.updateQueueConfig(config);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
      fetchPrediction();
    } catch (err) {
      console.error('Failed to update config:', err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="view-header">
        <div className="view-title-group">
          <h2>Queue Intelligence & Predictive Dispatch</h2>
          <div className="view-subtitle">
            Upstream footfall velocity predictive formula chain with exponential smoothing
          </div>
        </div>

        {prediction?.should_open_counter ? (
          <div
            className="pulse-indicator"
            style={{
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              color: 'var(--accent-rose)',
            }}
          >
            <div className="pulse-dot" style={{ background: 'var(--accent-rose)', boxShadow: '0 0 10px var(--accent-rose)' }} />
            <span>DISPATCH RECOMMENDATION: OPEN COUNTER</span>
          </div>
        ) : (
          <div className="pulse-indicator live">
            <div className="pulse-dot" />
            <span>QUEUE EQUILIBRIUM OPTIMAL</span>
          </div>
        )}
      </div>

      {/* Break-Beam Sensor Simulation Grid */}
      <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Checkout Counters (Break-Beam Sensor Input)</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Hardware break-beam sensor feed or interactive simulation
            </p>
          </div>
          <span className="chip-tag">Hardware Agnostic</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
          {['counter_1', 'counter_2', 'counter_3', 'counter_4'].map((cid, idx) => {
            const count = queueSizes[cid] || 0;
            const isOpen = count > 0 || idx < 2;

            return (
              <div
                key={cid}
                style={{
                  background: 'rgba(7, 10, 19, 0.7)',
                  borderRadius: '12px',
                  padding: '1.25rem',
                  border: isOpen ? '1px solid var(--border-cyan)' : '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-secondary)' }}>
                    COUNTER #{idx + 1}
                  </span>
                  <span
                    style={{
                      fontSize: '0.65rem',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      background: isOpen ? 'rgba(16, 185, 129, 0.15)' : 'rgba(100, 116, 139, 0.15)',
                      color: isOpen ? 'var(--accent-emerald)' : 'var(--text-muted)',
                      fontWeight: 600,
                    }}
                  >
                    {isOpen ? 'ACTIVE' : 'STANDBY'}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
                  <span style={{ fontSize: '2.4rem', fontWeight: 800, color: '#ffffff' }}>
                    {count}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>shoppers waiting</span>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => handleDecrement(cid)}
                    className="btn-secondary"
                    style={{ flex: 1, justifyContent: 'center' }}
                    title="Customer checkout complete"
                  >
                    - Served
                  </button>
                  <button
                    onClick={() => handleIncrement(cid)}
                    className="btn-primary"
                    style={{ flex: 1, justifyContent: 'center' }}
                    title="Customer joins queue"
                  >
                    + Joined
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Formula Chain Breakdown & Configuration */}
      <div className="grid-2col">
        {/* Formula Visualizer */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Predictive Formula Chain</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Live evaluation of upstream arrival demand vs checkout service capacity
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
            <div style={{ padding: '0.65rem 0.85rem', background: 'rgba(7, 10, 19, 0.5)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>1. SERVICE RATE (μ = 1 / avg_service_time)</div>
              <div style={{ color: 'var(--accent-cyan)', fontWeight: 600, marginTop: '2px' }}>
                {prediction?.service_rate_per_counter.toFixed(4) || '0.0222'} persons/sec/counter
              </div>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'rgba(7, 10, 19, 0.5)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>2. TOTAL CAPACITY (C × μ)</div>
              <div style={{ color: 'var(--accent-emerald)', fontWeight: 600, marginTop: '2px' }}>
                {prediction?.total_capacity.toFixed(4) || '0.0444'} persons/sec ({prediction?.counters_open || 1} open)
              </div>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'rgba(7, 10, 19, 0.5)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>3. CHECKOUT DEMAND (smoothed_footfall × conversion)</div>
              <div style={{ color: 'var(--accent-amber)', fontWeight: 600, marginTop: '2px' }}>
                {prediction?.predicted_checkout_demand.toFixed(4) || '0.0500'} persons/sec
              </div>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'rgba(7, 10, 19, 0.5)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>4. CONGESTION GAP (demand - capacity)</div>
              <div style={{ color: (prediction?.congestion_gap || 0) > 0 ? 'var(--accent-rose)' : 'var(--accent-emerald)', fontWeight: 600, marginTop: '2px' }}>
                {(prediction?.congestion_gap || 0) > 0 ? '+' : ''}{prediction?.congestion_gap.toFixed(4) || '0.0056'} persons/sec
              </div>
            </div>

            <div style={{ padding: '0.75rem 0.85rem', background: 'rgba(13, 19, 34, 0.8)', borderRadius: '8px', border: '1px solid var(--border-active)' }}>
              <div style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: '0.75rem' }}>
                5. PREDICTED QUEUE vs MAX ACCEPTABLE
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                <div>
                  Predicted: <span style={{ color: 'var(--accent-cyan)', fontWeight: 800 }}>{prediction?.predicted_queue_size.toFixed(1) || '0.0'}</span>
                </div>
                <div>
                  Max Acceptable: <span style={{ color: 'var(--accent-amber)', fontWeight: 800 }}>{prediction?.max_acceptable_queue.toFixed(1) || '4.0'}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Dashboard Tuning Controls */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Tuning Parameters</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Configure operational thresholds for the store
            </p>
          </div>

          <form onSubmit={handleSaveConfig} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div className="form-group">
              <label className="form-label">Average Service Time (seconds)</label>
              <input
                type="number"
                value={config.avg_service_time_s}
                onChange={(e) => setConfig({ ...config, avg_service_time_s: Number(e.target.value) })}
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Estimated Conversion Rate (0.1 - 1.0)</label>
              <input
                type="number"
                step="0.05"
                value={config.conversion_rate}
                onChange={(e) => setConfig({ ...config, conversion_rate: Number(e.target.value) })}
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Max Acceptable Wait Time (seconds)</label>
              <input
                type="number"
                value={config.max_acceptable_wait_time_s}
                onChange={(e) => setConfig({ ...config, max_acceptable_wait_time_s: Number(e.target.value) })}
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Average In-Store Shopping Time (seconds)</label>
              <input
                type="number"
                value={config.avg_shopping_time_s}
                onChange={(e) => setConfig({ ...config, avg_shopping_time_s: Number(e.target.value) })}
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Exponential Smoothing Alpha (α = 0.3)</label>
              <input
                type="number"
                step="0.05"
                value={config.smoothing_alpha}
                onChange={(e) => setConfig({ ...config, smoothing_alpha: Number(e.target.value) })}
                className="form-input"
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem' }}>
              <button type="submit" className="btn-primary" disabled={isSaving}>
                {isSaving ? 'Saving...' : 'Apply Configuration'}
              </button>
              {saveSuccess && (
                <span style={{ fontSize: '0.8rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
                  ✓ Config updated live!
                </span>
              )}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
