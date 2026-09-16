import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

interface DwellTimeChartProps {
  zoneDwellData: Record<string, { count: number; total_time_s: number }>;
}

const ZONE_COLORS: Record<string, string> = {
  apparel: '#6366f1',
  electronics: '#ec4899',
  grocery: '#f59e0b',
  checkout: '#06b6d4',
  entrance: '#10b981',
};

export const DwellTimeChart: React.FC<DwellTimeChartProps> = ({ zoneDwellData }) => {
  const chartData = Object.entries(zoneDwellData).map(([zone, data]) => ({
    name: zone.charAt(0).toUpperCase() + zone.slice(1),
    zoneKey: zone.toLowerCase(),
    avgDwellSec: data.count > 0 ? Math.round(data.total_time_s / data.count) : 0,
    totalDwellSec: Math.round(data.total_time_s),
    visitorCount: data.count,
  }));

  // Fallback demo data if no dwell events yet
  const displayData =
    chartData.length > 0
      ? chartData
      : [
          { name: 'Apparel', zoneKey: 'apparel', avgDwellSec: 42, totalDwellSec: 336, visitorCount: 8 },
          { name: 'Electronics', zoneKey: 'electronics', avgDwellSec: 68, totalDwellSec: 408, visitorCount: 6 },
          { name: 'Grocery', zoneKey: 'grocery', avgDwellSec: 25, totalDwellSec: 375, visitorCount: 15 },
          { name: 'Checkout', zoneKey: 'checkout', avgDwellSec: 85, totalDwellSec: 1020, visitorCount: 12 },
        ];

  return (
    <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ fontSize: '1.15rem' }}>Zone Dwell Engagement</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Average qualifying dwell duration (seconds) per store zone
          </p>
        </div>
        <span className="chip-tag" style={{ background: 'rgba(99, 102, 241, 0.15)', borderColor: 'rgba(99, 102, 241, 0.4)', color: 'var(--accent-indigo)' }}>
          Two-Layer Filter Active
        </span>
      </div>

      <div style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={displayData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <XAxis
              dataKey="name"
              stroke="#64748b"
              fontSize={12}
              tickLine={false}
              axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
            />
            <YAxis
              stroke="#64748b"
              fontSize={12}
              tickLine={false}
              axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
              tickFormatter={(v) => `${v}s`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(13, 19, 34, 0.95)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '8px',
                boxShadow: '0 8px 30px rgba(0, 0, 0, 0.5)',
                color: '#ffffff',
                fontFamily: 'var(--font-main)',
              }}
              formatter={(value: any, name: any) => [
                name === 'avgDwellSec' ? `${value}s avg dwell` : value,
                name === 'avgDwellSec' ? 'Avg Dwell' : name,
              ]}
            />
            <Bar dataKey="avgDwellSec" radius={[6, 6, 0, 0]}>
              {displayData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={ZONE_COLORS[entry.zoneKey] || 'var(--accent-cyan)'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginTop: '0.5rem' }}>
        {displayData.map((d) => (
          <div
            key={d.name}
            style={{
              padding: '0.5rem 0.75rem',
              background: 'rgba(7, 10, 19, 0.5)',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{d.name}</div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: ZONE_COLORS[d.zoneKey] || 'white' }}>
              {d.avgDwellSec}s
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-secondary)' }}>
              {d.visitorCount} visitors
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
