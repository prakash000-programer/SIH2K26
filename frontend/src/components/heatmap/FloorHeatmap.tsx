import React, { useState } from 'react';
import type { HeatmapCell, LiveDetection } from '../../types';

interface FloorHeatmapProps {
  cells: HeatmapCell[];
  gridRows?: number;
  gridCols?: number;
  floorWidthM?: number;
  floorHeightM?: number;
  liveDetections?: LiveDetection[];
}

export const FloorHeatmap: React.FC<FloorHeatmapProps> = ({
  cells,
  gridRows = 10,
  gridCols = 10,
  floorWidthM = 5.0,
  floorHeightM = 5.0,
  liveDetections = [],
}) => {
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number; count: number } | null>(null);

  // Map cell list to a lookup key: `${row},${col}` -> count
  const cellMap = new Map<string, number>();
  let maxCount = 1;
  cells.forEach((c) => {
    cellMap.set(`${c.row},${c.col}`, c.count);
    if (c.count > maxCount) maxCount = c.count;
  });

  // Determine retail zone by row & col
  const getZone = (r: number, c: number): { name: string; color: string } => {
    if (r >= 8 && c <= 3) return { name: 'Entrance', color: '#10b981' };
    if (r <= 4 && c <= 4) return { name: 'Apparel', color: '#6366f1' };
    if (r <= 4 && c >= 5) return { name: 'Electronics', color: '#ec4899' };
    if (r >= 5 && r <= 7 && c >= 5) return { name: 'Grocery', color: '#f59e0b' };
    if (r >= 8 && c >= 6) return { name: 'Checkout', color: '#06b6d4' };
    return { name: 'Walkway', color: '#64748b' };
  };

  // Color interpolation based on intensity
  const getCellColor = (count: number) => {
    if (count === 0) return 'rgba(15, 23, 42, 0.4)';
    const intensity = Math.min(1, count / maxCount);
    if (intensity < 0.25) {
      return `rgba(6, 182, 212, ${0.2 + intensity * 0.4})`;
    } else if (intensity < 0.6) {
      return `rgba(245, 158, 11, ${0.4 + intensity * 0.4})`;
    } else {
      return `rgba(244, 63, 94, ${0.6 + intensity * 0.4})`;
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ fontSize: '1.15rem' }}>Store Floor Density Heatmap</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Grid mapping: {gridRows}x{gridCols} cells ({floorWidthM}m × {floorHeightM}m retail floor)
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
          <span>Low</span>
          <div style={{
            width: '80px',
            height: '8px',
            borderRadius: '4px',
            background: 'linear-gradient(90deg, rgba(6, 182, 212, 0.3), #f59e0b, #f43f5e)',
          }} />
          <span>Peak</span>
        </div>
      </div>

      <div style={{ position: 'relative', width: '100%', maxWidth: '520px', margin: '0 auto' }}>
        {/* Heatmap Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${gridCols}, 1fr)`,
            gridTemplateRows: `repeat(${gridRows}, 1fr)`,
            gap: '4px',
            background: 'rgba(7, 10, 19, 0.85)',
            padding: '12px',
            borderRadius: '12px',
            border: '1px solid var(--border-subtle)',
            aspectRatio: '1 / 1',
            position: 'relative',
          }}
        >
          {Array.from({ length: gridRows }).map((_, r) =>
            Array.from({ length: gridCols }).map((_, c) => {
              const count = cellMap.get(`${r},${c}`) || 0;
              const zone = getZone(r, c);
              const isSelected = selectedCell?.row === r && selectedCell?.col === c;

              return (
                <div
                  key={`${r}-${c}`}
                  onClick={() => setSelectedCell({ row: r, col: c, count })}
                  style={{
                    backgroundColor: getCellColor(count),
                    borderRadius: '4px',
                    border: isSelected ? '2px solid #ffffff' : '1px solid rgba(255, 255, 255, 0.05)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.15s ease',
                    position: 'relative',
                  }}
                  title={`Row: ${r}, Col: ${c} | Zone: ${zone.name} | Footfall: ${count}`}
                >
                  {count > 0 && (
                    <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'white' }}>
                      {count}
                    </span>
                  )}
                </div>
              );
            })
          )}

          {/* Live Person Tracking Dots Overlay */}
          {liveDetections.map((p) => {
            // If centroid_world is available [x, y], map to percentage coordinates
            let leftPct = 50;
            let topPct = 50;
            if (p.centroid_world) {
              leftPct = Math.min(95, Math.max(5, (p.centroid_world[0] / floorWidthM) * 100));
              topPct = Math.min(95, Math.max(5, (p.centroid_world[1] / floorHeightM) * 100));
            }

            return (
              <div
                key={`live-${p.track_id}`}
                style={{
                  position: 'absolute',
                  left: `${leftPct}%`,
                  top: `${topPct}%`,
                  transform: 'translate(-50%, -50%)',
                  pointerEvents: 'none',
                  zIndex: 20,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  transition: 'all 0.3s ease-out',
                }}
              >
                <div
                  style={{
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    background: '#10b981',
                    border: '2px solid #ffffff',
                    boxShadow: '0 0 10px #10b981',
                    animation: 'pulse-ring 1.5s infinite',
                  }}
                />
                <span
                  style={{
                    fontSize: '0.55rem',
                    fontWeight: 800,
                    background: 'rgba(0, 0, 0, 0.75)',
                    color: '#10b981',
                    padding: '1px 4px',
                    borderRadius: '4px',
                    marginTop: '2px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  #{p.track_id}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Zone Legend & Selected Cell Info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {[
            { name: 'Entrance', color: '#10b981' },
            { name: 'Apparel', color: '#6366f1' },
            { name: 'Electronics', color: '#ec4899' },
            { name: 'Grocery', color: '#f59e0b' },
            { name: 'Checkout', color: '#06b6d4' },
          ].map((z) => (
            <div key={z.name} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: z.color }} />
              <span style={{ color: 'var(--text-secondary)' }}>{z.name}</span>
            </div>
          ))}
        </div>

        {selectedCell && (
          <div style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
            Selected: [{selectedCell.row},{selectedCell.col}] ({getZone(selectedCell.row, selectedCell.col).name}) • {selectedCell.count} visits
          </div>
        )}
      </div>
    </div>
  );
};
