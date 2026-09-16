import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { HeatmapResponse, ManagerSummary, LiveDetection } from '../types';
import { FloorHeatmap } from '../components/heatmap/FloorHeatmap';
import { DwellTimeChart } from '../components/charts/DwellTimeChart';
import { FootfallCard } from '../components/charts/FootfallCard';
import { LiveCameraFeed } from '../components/camera/LiveCameraFeed';

interface ManagerViewProps {
  liveDetections: LiveDetection[];
  liveFootfallRate: number;
}

export const ManagerView: React.FC<ManagerViewProps> = ({ liveDetections, liveFootfallRate }) => {
  const [timeRange, setTimeRange] = useState<'15m' | '1h' | 'today' | '7d'>('1h');
  const [viewMode, setViewMode] = useState<'split' | 'camera' | 'heatmap'>('split');
  const [heatmapData, setHeatmapData] = useState<HeatmapResponse | null>(null);
  const [summary, setSummary] = useState<ManagerSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const now = Date.now() / 1000;
      let start = now - 3600;
      if (timeRange === '15m') start = now - 900;
      if (timeRange === 'today') start = now - 86400;
      if (timeRange === '7d') start = now - 7 * 86400;

      const [hm, summ] = await Promise.all([
        api.getHeatmap(start, now),
        api.getSummary(),
      ]);
      setHeatmapData(hm);
      setSummary(summ);
    } catch (err) {
      console.error('Failed to load manager view data:', err);
    } finally {
      setIsLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  const footfallIn = summary?.footfall.in || 0;
  const footfallOut = summary?.footfall.out || 0;
  const rate = liveFootfallRate > 0 ? liveFootfallRate : (summary?.footfall_rate_per_min || 0);

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Bar */}
      <div className="view-header">
        <div className="view-title-group">
          <h2>Store Manager Operations & Digital Twin</h2>
          <div className="view-subtitle">
            Live edge camera tracking, spatial density heatmaps, and physical retail footfall
            {isLoading && <span style={{ marginLeft: '8px', color: 'var(--accent-cyan)' }}>• Refreshing...</span>}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {/* Digital Twin View Selector */}
          <div style={{ display: 'flex', gap: '0.3rem', background: 'rgba(7, 10, 19, 0.6)', padding: '4px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
            <button
              onClick={() => setViewMode('split')}
              className={`role-tab-btn ${viewMode === 'split' ? 'active' : ''}`}
              style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            >
              ◫ Split Twin View
            </button>
            <button
              onClick={() => setViewMode('camera')}
              className={`role-tab-btn ${viewMode === 'camera' ? 'active' : ''}`}
              style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            >
              🎥 Live Camera Only
            </button>
            <button
              onClick={() => setViewMode('heatmap')}
              className={`role-tab-btn ${viewMode === 'heatmap' ? 'active' : ''}`}
              style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            >
              🗺️ Heatmap Only
            </button>
          </div>

          {/* Time Filters */}
          <div style={{ display: 'flex', gap: '0.3rem', background: 'rgba(7, 10, 19, 0.6)', padding: '4px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
            {(['15m', '1h', 'today', '7d'] as const).map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className="role-tab-btn"
                style={{
                  padding: '4px 10px',
                  fontSize: '0.75rem',
                  background: timeRange === r ? 'rgba(6, 182, 212, 0.2)' : 'transparent',
                  color: timeRange === r ? '#ffffff' : 'var(--text-secondary)',
                  border: timeRange === r ? '1px solid rgba(6, 182, 212, 0.4)' : 'none',
                }}
              >
                {r === '15m' ? '15m' : r === '1h' ? '1h' : r === 'today' ? 'Today' : '7d'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="metrics-grid">
        <div className="glass-panel metric-card">
          <div className="metric-label">
            <span>Live Store Occupancy</span>
            <span>👥</span>
          </div>
          <div className="metric-value">{Math.max(0, footfallIn - footfallOut)}</div>
          <div className="metric-subtext">
            <span style={{ color: 'var(--accent-cyan)' }}>● {liveDetections.length} tracked</span> currently in frame
          </div>
        </div>

        <div className="glass-panel metric-card">
          <div className="metric-label">
            <span>Total Entries Today</span>
            <span>🚪</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--accent-emerald)' }}>
            {footfallIn}
          </div>
          <div className="metric-subtext">
            <span>Directional IN line crossed</span>
          </div>
        </div>

        <div className="glass-panel metric-card">
          <div className="metric-label">
            <span>Qualified Dwell Events</span>
            <span>⏱️</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--accent-indigo)' }}>
            {summary?.dwell_event_count || 0}
          </div>
          <div className="metric-subtext">
            <span>&gt; 5.0s pass-through filtered</span>
          </div>
        </div>

        <div className="glass-panel metric-card">
          <div className="metric-label">
            <span>Peak Engagement Zone</span>
            <span>🔥</span>
          </div>
          <div className="metric-value" style={{ fontSize: '1.6rem', color: 'var(--accent-amber)' }}>
            {summary?.dwell_by_zone && Object.keys(summary.dwell_by_zone).length > 0
              ? Object.entries(summary.dwell_by_zone).sort((a, b) => b[1].total_time_s - a[1].total_time_s)[0][0].toUpperCase()
              : 'APPAREL'}
          </div>
          <div className="metric-subtext">
            <span>Highest total customer attention</span>
          </div>
        </div>
      </div>

      {/* Digital Twin Views: Live Camera + Floor Heatmap */}
      {viewMode === 'split' && (
        <div className="grid-2col">
          <LiveCameraFeed compact />
          <FloorHeatmap
            cells={heatmapData?.cells || []}
            gridRows={heatmapData?.grid_rows || 10}
            gridCols={heatmapData?.grid_cols || 10}
            floorWidthM={heatmapData?.floor_width_m || 5.0}
            floorHeightM={heatmapData?.floor_height_m || 5.0}
            liveDetections={liveDetections}
          />
        </div>
      )}

      {viewMode === 'camera' && (
        <div>
          <LiveCameraFeed />
        </div>
      )}

      {viewMode === 'heatmap' && (
        <div className="grid-2col">
          <FloorHeatmap
            cells={heatmapData?.cells || []}
            gridRows={heatmapData?.grid_rows || 10}
            gridCols={heatmapData?.grid_cols || 10}
            floorWidthM={heatmapData?.floor_width_m || 5.0}
            floorHeightM={heatmapData?.floor_height_m || 5.0}
            liveDetections={liveDetections}
          />
          <FootfallCard
            countIn={footfallIn}
            countOut={footfallOut}
            footfallRatePerMin={rate}
            isHighDensity={liveDetections.length >= 6}
          />
        </div>
      )}

      {/* Analytics Row: Footfall Card & Dwell Time Chart */}
      {viewMode !== 'heatmap' && (
        <div className="grid-2col">
          <FootfallCard
            countIn={footfallIn}
            countOut={footfallOut}
            footfallRatePerMin={rate}
            isHighDensity={liveDetections.length >= 6}
          />
          <DwellTimeChart zoneDwellData={summary?.dwell_by_zone || {}} />
        </div>
      )}
    </div>
  );
};

