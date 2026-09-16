import React, { useState } from 'react';
import { LiveCameraFeed } from '../components/camera/LiveCameraFeed';
import { MultiCameraView } from '../components/camera/MultiCameraView';
import type { LiveDetection } from '../types';

interface CameraViewProps {
  liveDetections: LiveDetection[];
}

export const CameraView: React.FC<CameraViewProps> = ({ liveDetections }) => {
  const [activeTab, setActiveTab] = useState<'stream' | 'multi' | 'telemetry'>('stream');

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="view-header">
        <div className="view-title-group">
          <h2>Live Edge Camera & People Tracking</h2>
          <div className="view-subtitle">
            Direct visual output from YOLOv8n object detection and ByteTrack multi-object tracking
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.4rem', background: 'rgba(7, 10, 19, 0.6)', padding: '4px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
          <button
            onClick={() => setActiveTab('stream')}
            className={`role-tab-btn ${activeTab === 'stream' ? 'active' : ''}`}
            style={{ padding: '4px 12px', fontSize: '0.8rem' }}
          >
            🎥 Live Video Stream
          </button>
          <button
            onClick={() => setActiveTab('multi')}
            className={`role-tab-btn ${activeTab === 'multi' ? 'active' : ''}`}
            style={{ padding: '4px 12px', fontSize: '0.8rem' }}
          >
            🔗 Multi-Camera Grid + Re-ID
          </button>
          <button
            onClick={() => setActiveTab('telemetry')}
            className={`role-tab-btn ${activeTab === 'telemetry' ? 'active' : ''}`}
            style={{ padding: '4px 12px', fontSize: '0.8rem' }}
          >
            📊 Detection Telemetry ({liveDetections.length})
          </button>
        </div>
      </div>

      {/* Main Video Player */}
      {activeTab === 'stream' && <LiveCameraFeed />}

      {/* Multi-Camera Grid + Re-ID */}
      {activeTab === 'multi' && <MultiCameraView />}

      {/* Live Tracked Shoppers Telemetry Table */}
      {activeTab !== 'multi' && (
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.1rem' }}>Active Track Ephemeral State</h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Real-time tracked person centroids and confidence scores (discarded upon camera exit)
            </p>
          </div>
          <span className="chip-tag" style={{ background: 'rgba(6, 182, 212, 0.15)', borderColor: 'rgba(6, 182, 212, 0.4)', color: 'var(--accent-cyan)' }}>
            Ephemeral Memory Buffer
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.65rem' }}>GLOBAL ID</th>
                <th style={{ padding: '0.65rem' }}>TRACK ID</th>
                <th style={{ padding: '0.65rem' }}>CAMERA</th>
                <th style={{ padding: '0.65rem' }}>GENDER (EDGE AI)</th>
                <th style={{ padding: '0.65rem' }}>LIVE DWELL TIME</th>
                <th style={{ padding: '0.65rem' }}>IMAGE CENTROID (PX)</th>
                <th style={{ padding: '0.65rem' }}>YOLO CONFIDENCE</th>
                <th style={{ padding: '0.65rem' }}>STATUS</th>
              </tr>
            </thead>
            <tbody>
              {liveDetections.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No people currently detected in the camera frame. Step into the webcam view to see real-time tracking!
                  </td>
                </tr>
              ) : (
                liveDetections.map((p) => (
                  <tr key={p.track_id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                    <td style={{ padding: '0.65rem', fontWeight: 700, color: p.global_id ? '#a78bfa' : 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {p.global_id ? `G#${p.global_id}` : '—'}
                    </td>
                    <td style={{ padding: '0.65rem', fontWeight: 700, color: 'var(--accent-emerald)' }}>
                      #{p.track_id}
                    </td>
                    <td style={{ padding: '0.65rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)', fontSize: '0.78rem' }}>
                      {p.camera_id || 'cam0'}
                    </td>
                    <td style={{ padding: '0.65rem' }}>
                      <span
                        className="chip-tag"
                        style={{
                          background: p.gender === 'Female' ? 'rgba(236, 72, 153, 0.15)' : 'rgba(6, 182, 212, 0.15)',
                          borderColor: p.gender === 'Female' ? 'rgba(236, 72, 153, 0.4)' : 'rgba(6, 182, 212, 0.4)',
                          color: p.gender === 'Female' ? '#f472b6' : 'var(--accent-cyan)',
                          fontWeight: 600,
                        }}
                      >
                        {p.gender === 'Female' ? '♀ Female' : '♂ Male'}
                        {p.gender_confidence ? ` (${Math.round(p.gender_confidence * 100)}%)` : ''}
                      </span>
                    </td>
                    <td style={{ padding: '0.65rem', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--accent-amber)' }}>
                      ⏱ {typeof p.dwell_time_s === 'number' ? `${p.dwell_time_s.toFixed(1)}s` : '0.0s'}
                    </td>
                    <td style={{ padding: '0.65rem', fontFamily: 'var(--font-mono)' }}>
                      ({Math.round(p.centroid_px[0])}px, {Math.round(p.centroid_px[1])}px)
                    </td>
                    <td style={{ padding: '0.65rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)' }}>
                      {p.centroid_world
                        ? `${p.centroid_world[0].toFixed(2)}m, ${p.centroid_world[1].toFixed(2)}m`
                        : 'Uncalibrated'}
                    </td>
                    <td style={{ padding: '0.65rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <div style={{ width: '60px', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ width: `${Math.round(p.confidence * 100)}%`, height: '100%', background: 'var(--accent-emerald)' }} />
                        </div>
                        <span style={{ fontSize: '0.75rem' }}>{Math.round(p.confidence * 100)}%</span>
                      </div>
                    </td>
                    <td style={{ padding: '0.65rem' }}>
                      <span className="chip-tag" style={{ background: 'rgba(16, 185, 129, 0.15)', borderColor: 'var(--accent-emerald)', color: 'var(--accent-emerald)' }}>
                        Active Track
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      )}
    </div>
  );
};
