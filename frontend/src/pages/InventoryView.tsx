import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { InventorySlot } from '../types';

export const InventoryView: React.FC = () => {
  const [slots, setSlots] = useState<InventorySlot[]>([]);
  const [newSlotName, setNewSlotName] = useState('');
  const [newSlotStock, setNewSlotStock] = useState(24);

  // POS Sale Form State
  const [selectedSlotForSale, setSelectedSlotForSale] = useState('');
  const [saleQuantity, setSaleQuantity] = useState(1);
  const [saleMessage, setSaleMessage] = useState('');

  // Shelf Check State
  const [shelfSlotName, setShelfSlotName] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [checkResult, setCheckResult] = useState<{
    diff_ratio: number;
    is_empty: boolean;
    stockout_fired: boolean;
  } | null>(null);
  const [isChecking, setIsChecking] = useState(false);

  const loadSlots = useCallback(async () => {
    try {
      const data = await api.getInventorySlots();
      setSlots(data.slots || []);
      if (data.slots && data.slots.length > 0 && !selectedSlotForSale) {
        setSelectedSlotForSale(data.slots[0].slot_name);
        setShelfSlotName(data.slots[0].slot_name);
      }
    } catch (err) {
      console.error('Failed to load slots:', err);
    }
  }, [selectedSlotForSale]);

  useEffect(() => {
    loadSlots();
  }, [loadSlots]);

  const handleCreateSlot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSlotName.trim()) return;
    try {
      await api.createSlot(newSlotName.trim(), newSlotStock);
      setNewSlotName('');
      loadSlots();
    } catch (err) {
      console.error(err);
    }
  };

  const handleRecordSale = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSlotForSale) return;
    try {
      await api.recordSale(selectedSlotForSale, saleQuantity);
      setSaleMessage(`✓ Recorded sale of ${saleQuantity} unit(s) for "${selectedSlotForSale}"`);
      setTimeout(() => setSaleMessage(''), 3000);
      loadSlots();
    } catch (err) {
      console.error(err);
    }
  };

  const handleCheckShelf = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!shelfSlotName || !selectedFile) return;
    setIsChecking(true);
    try {
      const res = await api.checkShelf(shelfSlotName, selectedFile);
      setCheckResult(res);
      loadSlots();
    } catch (err: any) {
      alert(`Shelf check error: ${err.message || err}`);
    } finally {
      setIsChecking(false);
    }
  };

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="view-header">
        <div className="view-title-group">
          <h2>Shelf Inventory & Stock Monitoring</h2>
          <div className="view-subtitle">
            Zero-image storage frame differencing with 3-consecutive consensus alert filtering
          </div>
        </div>

        <span className="chip-tag" style={{ background: 'rgba(99, 102, 241, 0.15)', borderColor: 'rgba(99, 102, 241, 0.4)', color: 'var(--accent-indigo)' }}>
          Privacy: Hashes Only Persisted
        </span>
      </div>

      {/* Roadmap Notice */}
      <div
        style={{
          background: 'rgba(99, 102, 241, 0.08)',
          border: '1px solid rgba(99, 102, 241, 0.25)',
          borderRadius: '12px',
          padding: '1rem 1.25rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
        }}
      >
        <div style={{ fontSize: '1.5rem' }}>📌</div>
        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
          <strong style={{ color: '#ffffff' }}>[ROADMAP ARCHITECTURE]:</strong> Planogram layout & SKU-level position compliance will be enabled with fine-tuned YOLO on the Qualcomm QCS6490 NPU. For this edge prototype, fast pixel differencing + 3-consecutive consensus provides real-time stock-out detection.
        </div>
      </div>

      {/* Slots Table */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Monitored Shelf Slots</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Stock level calculation: Available = Total - Sold
            </p>
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.75rem' }}>SLOT NAME</th>
                <th style={{ padding: '0.75rem' }}>TOTAL STOCK</th>
                <th style={{ padding: '0.75rem' }}>POS SOLD</th>
                <th style={{ padding: '0.75rem' }}>AVAILABLE</th>
                <th style={{ padding: '0.75rem' }}>EMPTY SCANS (CONSENSUS)</th>
                <th style={{ padding: '0.75rem' }}>STATUS</th>
              </tr>
            </thead>
            <tbody>
              {slots.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No shelf slots registered yet. Add a slot below.
                  </td>
                </tr>
              ) : (
                slots.map((s) => {
                  const available = Math.max(0, s.total_stock - s.sold);
                  const isStockedOut = s.is_stocked_out === 1 || available === 0;

                  return (
                    <tr
                      key={s.id}
                      style={{
                        borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                        background: isStockedOut ? 'rgba(239, 68, 68, 0.06)' : 'transparent',
                      }}
                    >
                      <td style={{ padding: '0.75rem', fontWeight: 600, color: '#ffffff' }}>
                        {s.slot_name}
                      </td>
                      <td style={{ padding: '0.75rem' }}>{s.total_stock} units</td>
                      <td style={{ padding: '0.75rem', color: 'var(--accent-amber)' }}>{s.sold} units</td>
                      <td style={{ padding: '0.75rem', fontWeight: 700, color: available > 5 ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>
                        {available} units
                      </td>
                      <td style={{ padding: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          {[1, 2, 3].map((step) => (
                            <span
                              key={step}
                              style={{
                                width: '10px',
                                height: '10px',
                                borderRadius: '50%',
                                background: s.consecutive_empty >= step ? 'var(--accent-rose)' : 'rgba(255,255,255,0.1)',
                                display: 'inline-block',
                              }}
                              title={`Scan ${step}/3`}
                            />
                          ))}
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '4px' }}>
                            ({s.consecutive_empty}/3)
                          </span>
                        </div>
                      </td>
                      <td style={{ padding: '0.75rem' }}>
                        {isStockedOut ? (
                          <span className="chip-tag" style={{ background: 'rgba(239, 68, 68, 0.2)', borderColor: 'var(--accent-rose)', color: 'var(--accent-rose)' }}>
                            Stocked Out
                          </span>
                        ) : available <= 5 ? (
                          <span className="chip-tag" style={{ background: 'rgba(245, 158, 11, 0.2)', borderColor: 'var(--accent-amber)', color: 'var(--accent-amber)' }}>
                            Low Stock
                          </span>
                        ) : (
                          <span className="chip-tag" style={{ background: 'rgba(16, 185, 129, 0.15)', borderColor: 'var(--accent-emerald)', color: 'var(--accent-emerald)' }}>
                            In Stock
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* POS Sale Form & Tools */}
      <div className="grid-2col">
        {/* Mock POS Sale Form */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Mock POS Checkout Input</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Simulates cashier bar-code scan or POS webhook: decrements available stock
            </p>
          </div>

          <form onSubmit={handleRecordSale} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div className="form-group">
              <label className="form-label">Select Shelf Slot</label>
              <select
                value={selectedSlotForSale}
                onChange={(e) => setSelectedSlotForSale(e.target.value)}
                className="form-select"
              >
                {slots.map((s) => (
                  <option key={s.id} value={s.slot_name}>
                    {s.slot_name} (Avail: {Math.max(0, s.total_stock - s.sold)})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Quantity Sold</label>
              <input
                type="number"
                min="1"
                max="50"
                value={saleQuantity}
                onChange={(e) => setSaleQuantity(Number(e.target.value))}
                className="form-input"
              />
            </div>

            <button type="submit" className="btn-primary" style={{ marginTop: '0.5rem' }}>
              💳 Record Sale & Decrement Stock
            </button>

            {saleMessage && (
              <div style={{ fontSize: '0.85rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
                {saleMessage}
              </div>
            )}
          </form>
        </div>

        {/* Shelf Camera Differencing Simulator */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem' }}>Shelf Camera Verification</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              In-memory frame differencing test (no images saved to disk)
            </p>
          </div>

          <form onSubmit={handleCheckShelf} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div className="form-group">
              <label className="form-label">Target Shelf Slot</label>
              <select
                value={shelfSlotName}
                onChange={(e) => setShelfSlotName(e.target.value)}
                className="form-select"
              >
                {slots.map((s) => (
                  <option key={s.id} value={s.slot_name}>
                    {s.slot_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Upload Current Snapshot Frame</label>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="form-input"
                style={{ padding: '0.4rem' }}
              />
            </div>

            <button
              type="submit"
              className="btn-secondary"
              disabled={isChecking || !selectedFile}
              style={{ marginTop: '0.5rem' }}
            >
              {isChecking ? 'Running OpenCV Diff...' : '📷 Run Shelf Differencing Check'}
            </button>

            {checkResult && (
              <div style={{ padding: '0.75rem', background: 'rgba(7, 10, 19, 0.6)', borderRadius: '8px', border: '1px solid var(--border-subtle)', fontSize: '0.8rem' }}>
                <div>Diff Ratio: <strong>{(checkResult.diff_ratio * 100).toFixed(1)}%</strong></div>
                <div>Status: <strong style={{ color: checkResult.is_empty ? 'var(--accent-rose)' : 'var(--accent-emerald)' }}>{checkResult.is_empty ? 'EMPTY / DEPLETED' : 'OCCUPIED / STOCKED'}</strong></div>
                {checkResult.stockout_fired && (
                  <div style={{ color: 'var(--accent-rose)', fontWeight: 700, marginTop: '4px' }}>
                    🚨 3-Consecutive Consensus Reached: Stockout Alert Broadcasted!
                  </div>
                )}
              </div>
            )}
          </form>
        </div>
      </div>

      {/* Add New Shelf Slot Form */}
      <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '1.15rem' }}>Register New Shelf Slot</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Define a new physical retail shelf slot for camera surveillance
          </p>
        </div>

        <form onSubmit={handleCreateSlot} style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: 1, minWidth: '220px', marginBottom: 0 }}>
            <label className="form-label">Slot Name / SKU Description</label>
            <input
              type="text"
              placeholder="e.g. Slot C - Snack Bars"
              value={newSlotName}
              onChange={(e) => setNewSlotName(e.target.value)}
              className="form-input"
            />
          </div>

          <div className="form-group" style={{ width: '160px', marginBottom: 0 }}>
            <label className="form-label">Initial Stock Capacity</label>
            <input
              type="number"
              min="1"
              value={newSlotStock}
              onChange={(e) => setNewSlotStock(Number(e.target.value))}
              className="form-input"
            />
          </div>

          <button type="submit" className="btn-secondary" style={{ height: '42px' }}>
            + Register Slot
          </button>
        </form>
      </div>
    </div>
  );
};
