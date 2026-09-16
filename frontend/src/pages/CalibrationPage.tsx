import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { CalibrationStatus } from '../types';

export const CalibrationPage: React.FC = () => {
  const [status, setStatus] = useState<CalibrationStatus | null>(null);
  const [floorWidth, setFloorWidth] = useState(5.0);
  const [floorHeight, setFloorHeight] = useState(5.0);

  // 4 image pixel points
  const [p1, setP1] = useState<[number, number]>([120, 100]);
  const [p2, setP2] = useState<[number, number]>([520, 100]);
  const [p3, setP3] = useState<[number, number]>([600, 420]);
  const [p4, setP4] = useState<[number, number]>([40, 420]);

  // 4 real-world meter points
  const [w1, setW1] = useState<[number, number]>([0.0, 0.0]);
  const [w2, setW2] = useState<[number, number]>([5.0, 0.0]);
  const [w3, setW3] = useState<[number, number]>([5.0, 5.0]);
  const [w4, setW4] = useState<[number, number]>([0.0, 5.0]);

  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');

  const loadStatus = async () => {
    try {
      const s = await api.getCalibrationStatus();
      setStatus(s);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await api.setCalibrationPoints({
        pixel_points: [p1, p2, p3, p4],
        world_points: [w1, w2, w3, w4],
        floor_width_m: floorWidth,
        floor_height_m: floorHeight,
      });
      setMessage('✓ Homography Matrix computed and persisted successfully!');
      setTimeout(() => setMessage(''), 4000);
      loadStatus();
    } catch (err: any) {
      setMessage(`Calibration Error: ${err.message || err}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="view-header">
        <div className="view-title-group">
          <h2>Perspective Camera Calibration</h2>
          <div className="view-subtitle">
            Homography matrix estimation: maps perspective webcam pixels to metric (x,y) floor coordinates
          </div>
        </div>

        <div className="pulse-indicator live">
          <div className="pulse-dot" />
          <span>STATUS: {status?.calibrated ? 'CALIBRATED' : 'DEFAULT CONFIG'}</span>
        </div>
      </div>

      <div className="grid-2col">
        {/* Interactive Mapping Visualizer */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Perspective Transformation</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Webcam Angled Frame → Bird's Eye Metric Coordinate Plane
            </p>
          </div>

          <div
            style={{
              aspectRatio: '16 / 9',
              background: 'radial-gradient(circle at 50% 50%, #111827 0%, #030712 100%)',
              borderRadius: '12px',
              border: '1px solid var(--border-subtle)',
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            {/* Trapezoid visual overlay */}
            <svg style={{ position: 'absolute', width: '100%', height: '100%', top: 0, left: 0 }}>
              <polygon
                points="20%,25% 80%,25% 92%,85% 8%,85%"
                fill="rgba(6, 182, 212, 0.1)"
                stroke="var(--accent-cyan)"
                strokeWidth="2"
                strokeDasharray="4 4"
              />
              <circle cx="20%" cy="25%" r="6" fill="#10b981" />
              <text x="21%" y="22%" fill="#10b981" fontSize="12" fontWeight="700">P1 (0,0)</text>

              <circle cx="80%" cy="25%" r="6" fill="#6366f1" />
              <text x="74%" y="22%" fill="#6366f1" fontSize="12" fontWeight="700">P2 (5m,0)</text>

              <circle cx="92%" cy="85%" r="6" fill="#f43f5e" />
              <text x="78%" y="82%" fill="#f43f5e" fontSize="12" fontWeight="700">P3 (5m,5m)</text>

              <circle cx="8%" cy="85%" r="6" fill="#f59e0b" />
              <text x="9%" y="82%" fill="#f59e0b" fontSize="12" fontWeight="700">P4 (0,5m)</text>
            </svg>

            <div style={{ zIndex: 10, textAlign: 'center', pointerEvents: 'none' }}>
              <span style={{ fontSize: '1.2rem', color: 'var(--text-secondary)' }}>🎥 Monitored Camera Field</span>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                4 Reference points define metric floor boundary
              </div>
            </div>
          </div>

          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', background: 'rgba(7, 10, 19, 0.5)', padding: '0.75rem', borderRadius: '8px' }}>
            💡 <strong>Tip:</strong> For physical setup, you can also run <code>python scripts/calibrate.py</code> to interactively click reference points on your live webcam window.
          </div>
        </div>

        {/* Coordinate Points Form */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Reference Point Correspondences</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Set pixel (X, Y) to real world (meters) coordinates
            </p>
          </div>

          <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label">Floor Width (meters)</label>
                <input
                  type="number"
                  step="0.5"
                  value={floorWidth}
                  onChange={(e) => setFloorWidth(Number(e.target.value))}
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Floor Length (meters)</label>
                <input
                  type="number"
                  step="0.5"
                  value={floorHeight}
                  onChange={(e) => setFloorHeight(Number(e.target.value))}
                  className="form-input"
                />
              </div>
            </div>

            {/* Points Inputs */}
            {[
              { label: 'Point 1 (Top-Left)', p: p1, setP: setP1, w: w1, setW: setW1, color: '#10b981' },
              { label: 'Point 2 (Top-Right)', p: p2, setP: setP2, w: w2, setW: setW2, color: '#6366f1' },
              { label: 'Point 3 (Bottom-Right)', p: p3, setP: setP3, w: w3, setW: setW3, color: '#f43f5e' },
              { label: 'Point 4 (Bottom-Left)', p: p4, setP: setP4, w: w4, setW: setW4, color: '#f59e0b' },
            ].map((pt, i) => (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1.2fr 1fr 1fr',
                  gap: '0.5rem',
                  alignItems: 'center',
                  background: 'rgba(7, 10, 19, 0.4)',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: pt.color }}>
                  {pt.label}
                </span>
                <input
                  type="text"
                  placeholder="Pixel px,py"
                  value={`${pt.p[0]}, ${pt.p[1]}`}
                  onChange={(e) => {
                    const parts = e.target.value.split(',').map((v) => Number(v.trim()) || 0);
                    if (parts.length === 2) pt.setP([parts[0], parts[1]]);
                  }}
                  className="form-input"
                  style={{ fontSize: '0.8rem', padding: '0.35rem 0.6rem' }}
                />
                <input
                  type="text"
                  placeholder="World x,y (m)"
                  value={`${pt.w[0]}, ${pt.w[1]}`}
                  onChange={(e) => {
                    const parts = e.target.value.split(',').map((v) => Number(v.trim()) || 0);
                    if (parts.length === 2) pt.setW([parts[0], parts[1]]);
                  }}
                  className="form-input"
                  style={{ fontSize: '0.8rem', padding: '0.35rem 0.6rem' }}
                />
              </div>
            ))}

            <button type="submit" className="btn-primary" style={{ marginTop: '0.75rem' }} disabled={isSaving}>
              {isSaving ? 'Computing Matrix...' : '💾 Compute & Save Homography'}
            </button>

            {message && (
              <div style={{ fontSize: '0.85rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
                {message}
              </div>
            )}
          </form>
        </div>
      </div>
    </div>
  );
};
