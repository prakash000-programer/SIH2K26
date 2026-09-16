import React, { useState, useEffect, useCallback } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Header } from './components/layout/Header';
import { ManagerView } from './pages/ManagerView';
import { StaffView } from './pages/StaffView';
import { OwnerView } from './pages/OwnerView';
import { QueueView } from './pages/QueueView';
import { InventoryView } from './pages/InventoryView';
import { CalibrationPage } from './pages/CalibrationPage';
import { CameraView } from './pages/CameraView';
import { useWebSocket } from './hooks/useWebSocket';
import type { AlertItem, LiveDetection } from './types';
import { api } from './api/client';

const MainContent: React.FC = () => {
  const { role } = useAuth();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [liveDetections, setLiveDetections] = useState<LiveDetection[]>([]);
  const [liveFootfallRate, setLiveFootfallRate] = useState<number>(0);
  const [queueSizes, setQueueSizes] = useState<Record<string, number>>({});

  const refreshQueues = useCallback(async () => {
    try {
      const data = await api.getQueueStatus();
      setQueueSizes(data.queues || {});
    } catch (err) {
      // ignore
    }
  }, []);

  useEffect(() => {
    refreshQueues();
    const interval = setInterval(refreshQueues, 8000);
    return () => clearInterval(interval);
  }, [refreshQueues]);

  // WebSocket hook connection
  const { isConnected } = useWebSocket({
    role,
    onDetection: (data) => {
      setLiveDetections(data.persons || []);
    },
    onFootfall: () => {
      setLiveFootfallRate((prev) => prev + 0.2);
    },
    onQueueUpdate: (data) => {
      setQueueSizes(data.all_queues || {});
    },
    onAlert: (alert) => {
      setAlerts((prev) => [alert, ...prev.slice(0, 19)]);
    },
  });

  const dismissAlert = (id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header wsConnected={isConnected} alertCount={alerts.length} />

      <main className="app-container" style={{ flex: 1 }}>
        {role === 'manager' && (
          <ManagerView liveDetections={liveDetections} liveFootfallRate={liveFootfallRate} />
        )}
        {role === 'camera' && (
          <CameraView liveDetections={liveDetections} />
        )}
        {role === 'staff' && (
          <StaffView
            alerts={alerts}
            onDismissAlert={dismissAlert}
            queueSizes={queueSizes}
            onQueueChange={refreshQueues}
          />
        )}
        {role === 'owner' && <OwnerView />}
        {role === 'queue' && (
          <QueueView queueSizes={queueSizes} onQueueChange={refreshQueues} />
        )}
        {role === 'inventory' && <InventoryView />}
        {role === 'calibration' && <CalibrationPage />}
      </main>

      {/* Global Footer */}
      <footer
        style={{
          borderTop: '1px solid var(--border-subtle)',
          padding: '1.25rem 2rem',
          background: 'rgba(7, 10, 19, 0.95)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <strong style={{ color: 'var(--text-primary)' }}>IntelliSales</strong>
          <span>Smart India Hackathon • PS: SIH26179</span>
          <span>•</span>
          <span style={{ color: 'var(--accent-cyan)' }}>Hardware: Qualcomm QCS6490 Edge Target</span>
        </div>

        <div>
          Privacy Guaranteed: Real-time OpenCV/YOLO inference with zero image/frame disk persistence.
        </div>
      </footer>
    </div>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <MainContent />
    </AuthProvider>
  );
}
