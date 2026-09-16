import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { ROIResponse } from '../types';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

export const OwnerView: React.FC = () => {
  const [baselineRevenue, setBaselineRevenue] = useState<number>(35000);
  const [roiData, setRoiData] = useState<ROIResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchROI = useCallback(async (revenue: number) => {
    setIsLoading(true);
    try {
      const data = await api.calculateROI(revenue);
      setRoiData(data);
    } catch (err) {
      console.error('Failed to calculate ROI:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchROI(baselineRevenue);
  }, [fetchROI]);

  const handleRecalculate = (e: React.FormEvent) => {
    e.preventDefault();
    fetchROI(baselineRevenue);
  };

  // Generate 12-month projection data for chart
  const monthlyCost = roiData?.monthly_system_cost || 150;
  const monthlyBenefit = Math.max(0, roiData?.total_monthly_benefit || 2800);

  const projectionData = Array.from({ length: 12 }, (_, i) => {
    const month = i + 1;
    const cumBenefit = Math.round(monthlyBenefit * month);
    const cumCost = Math.round(monthlyCost * month + 500); // 500 initial edge hardware amortized
    return {
      month: `M${month}`,
      cumulativeBenefit: cumBenefit,
      cumulativeCost: cumCost,
      netProfit: cumBenefit - cumCost,
    };
  });

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="view-header">
        <div className="view-title-group">
          <h2>Executive Financial ROI & Impact</h2>
          <div className="view-subtitle">
            Measurable store economics, conversion uplift, and payback timeline from IntelliSales Edge AI
          </div>
        </div>

        <form onSubmit={handleRecalculate} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Baseline Monthly Rev ($):</span>
            <input
              type="number"
              value={baselineRevenue}
              onChange={(e) => setBaselineRevenue(Number(e.target.value))}
              className="form-input"
              style={{ width: '130px', padding: '0.4rem 0.6rem' }}
            />
          </div>
          <button type="submit" className="btn-primary" style={{ padding: '0.45rem 1rem', fontSize: '0.85rem' }} disabled={isLoading}>
            {isLoading ? 'Computing...' : 'Recalculate'}
          </button>
        </form>
      </div>

      {/* ROI Cards */}
      <div className="metrics-grid">
        <div className="glass-panel metric-card">
          <div className="metric-label">
            <span>Total Monthly Benefit</span>
            <span>💰</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--accent-emerald)' }}>
            ${(roiData?.total_monthly_benefit || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className="metric-subtext">
            <span>Revenue uplift + stockouts saved</span>
          </div>
        </div>

        <div className="glass-panel metric-card">
          <div className="metric-label">
            <span>Return On Investment</span>
            <span>📈</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--accent-cyan)' }}>
            {(roiData?.monthly_roi_percent || 0).toFixed(1)}%
          </div>
          <div className="metric-subtext">
            <span>Monthly benefit vs ${roiData?.monthly_system_cost || 150} system cost</span>
          </div>
        </div>

        <div className="glass-panel metric-card">
          <div className="metric-label">
            <span>Payback Period</span>
            <span>⚡</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--accent-indigo)' }}>
            {roiData?.payback_month === -1 ? '> 36 mo' : `${roiData?.payback_month || 1} Month`}
          </div>
          <div className="metric-subtext">
            <span>Break-even timeline achieved</span>
          </div>
        </div>

        <div className="glass-panel metric-card">
          <div className="metric-label">
            <span>Stockouts Prevented</span>
            <span>🛡️</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--accent-amber)' }}>
            ${(roiData?.stockouts_prevented_value || 0).toLocaleString()}
          </div>
          <div className="metric-subtext">
            <span>Protected lost sales value</span>
          </div>
        </div>
      </div>

      {/* Financial Trajectory Chart & Breakdown */}
      <div className="grid-2col">
        {/* Cumulative Benefit vs Cost */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>12-Month Cumulative Profit Trajectory</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Cumulative financial return vs cumulative edge operational cost
            </p>
          </div>

          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={projectionData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorBenefit" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="month" stroke="#64748b" fontSize={12} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={12} tickLine={false} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(13, 19, 34, 0.95)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    color: '#ffffff',
                    fontFamily: 'var(--font-main)',
                  }}
                  formatter={(value: any) => [`$${Number(value).toLocaleString()}`, '']}
                />
                <Legend wrapperStyle={{ fontSize: '0.8rem', paddingTop: '10px' }} />
                <Area
                  type="monotone"
                  dataKey="cumulativeBenefit"
                  name="Cumulative Benefit ($)"
                  stroke="#10b981"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorBenefit)"
                />
                <Area
                  type="monotone"
                  dataKey="cumulativeCost"
                  name="Cumulative Cost ($)"
                  stroke="#ef4444"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorCost)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Economic Drivers Breakdown */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Core Financial Drivers</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Variables powering the intelligence-driven revenue model
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'rgba(7, 10, 19, 0.5)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Monthly Footfall IN</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Live counted store visitors</div>
              </div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'white' }}>
                {(roiData?.live_footfall || 0).toLocaleString()} shoppers
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'rgba(7, 10, 19, 0.5)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Checkout Conversion Rate</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Shoppers that complete purchase</div>
              </div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                {((roiData?.conversion_rate || 0.3) * 100).toFixed(1)}%
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'rgba(7, 10, 19, 0.5)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Average Basket Value</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Gross transaction average</div>
              </div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--accent-emerald)' }}>
                ${(roiData?.avg_basket_value || 25).toFixed(2)}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'rgba(7, 10, 19, 0.5)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Monthly Edge Platform Cost</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Compute & local maintenance</div>
              </div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--accent-rose)' }}>
                ${(roiData?.monthly_system_cost || 150).toFixed(2)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
