import React, { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE, api } from '../../api/client';
import type { CameraInfo, GlobalTrack } from '../../types';

/**
 * MultiCameraView — Displays a grid of all active camera feeds with:
 * - Composite grid MJPEG stream from the backend
 * - In-browser mobile device camera streaming (WebRTC / getUserMedia -> Edge Hub)
 * - Global Re-ID tracker panel showing cross-camera person identities
 * - "Add Camera" modal to register new IP/mobile/webcam sources
 * - Per-camera status badges (FPS, track count, source type)
 */
export const MultiCameraView: React.FC = () => {
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [globalTracks, setGlobalTracks] = useState<GlobalTrack[]>([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [gridKey, setGridKey] = useState(Date.now());

  // Add camera form state
  const [newCamId, setNewCamId] = useState('');
  const [newCamName, setNewCamName] = useState('');
  const [newCamType, setNewCamType] = useState<'ip_camera' | 'webcam' | 'mobile_browser'>('mobile_browser');
  const [newCamUrl, setNewCamUrl] = useState('');
  const [newCamIndex, setNewCamIndex] = useState(0);
  const [autoStartStream, setAutoStartStream] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [addMessage, setAddMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Device camera streaming state (for streaming THIS device into a camera slot)
  const [streamingCamId, setStreamingCamId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment');
  const [streamFps, setStreamFps] = useState(0);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [showLocalPreview, setShowLocalPreview] = useState(false);
  const [viewMode, setViewMode] = useState<'grid' | string>('grid');

  const localVideoRef = useRef<HTMLVideoElement | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const streamTimerRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const isUploadingRef = useRef(false);
  const frameCountRef = useRef(0);

  // Poll camera list & global tracks
  const refreshData = useCallback(async () => {
    try {
      const [camRes, trackRes] = await Promise.all([
        api.listCameras(),
        api.getGlobalTracks(),
      ]);
      setCameras(camRes.cameras || []);
      setGlobalTracks(trackRes.tracks || []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 2000);
    return () => clearInterval(interval);
  }, [refreshData]);

  // Clean up streaming on unmount
  useEffect(() => {
    return () => {
      stopDeviceStream();
    };
  }, []);

  // --- Device Camera Streaming Logic (Ultra-fast WebSocket / getUserMedia) ---
  const startDeviceStream = async (targetCamId: string, customFacing?: 'environment' | 'user') => {
    try {
      setStreamError(null);
      const activeFacing = customFacing || facingMode;

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error(
          'Mobile browsers strictly require HTTPS to access the camera. Make sure you are visiting this dashboard via https://'
        );
      }

      // Stop previous tracks if any
      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach((t) => t.stop());
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: activeFacing },
          width: { ideal: 480 },
          height: { ideal: 360 },
        },
        audio: false,
      });

      localStreamRef.current = stream;
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
        await localVideoRef.current.play();
      }

      // Open low-latency binary WebSocket connection
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api/video/ws-stream-in?camera_id=${targetCamId}`;
      try {
        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'blob';
        wsRef.current = ws;
      } catch {
        wsRef.current = null;
      }

      setStreamingCamId(targetCamId);
      setIsStreaming(true);
      frameCountRef.current = 0;
      isUploadingRef.current = false;

      // Start frame capture loop (~28-30 FPS)
      const canvas = document.createElement('canvas');
      canvas.width = 480;
      canvas.height = 360;
      const ctx = canvas.getContext('2d');

      let lastFpsTime = Date.now();
      let framesThisSec = 0;

      if (streamTimerRef.current) clearInterval(streamTimerRef.current);

      streamTimerRef.current = window.setInterval(() => {
        if (!localVideoRef.current || localVideoRef.current.readyState < 2) return;

        if (ctx) {
          ctx.drawImage(localVideoRef.current, 0, 0, 480, 360);
          canvas.toBlob(
            (blob) => {
              if (blob) {
                // Priority 1: WebSocket binary transmission (<10ms latency)
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                  wsRef.current.send(blob);
                } else if (!isUploadingRef.current) {
                  // Fallback: HTTP POST
                  isUploadingRef.current = true;
                  fetch(`${API_BASE}/api/video/ingest-frame?camera_id=${targetCamId}`, {
                    method: 'POST',
                    body: blob,
                    headers: { 'Content-Type': 'image/jpeg' },
                  })
                    .catch(() => {})
                    .finally(() => {
                      isUploadingRef.current = false;
                    });
                }

                framesThisSec++;
                const now = Date.now();
                if (now - lastFpsTime >= 1000) {
                  setStreamFps(framesThisSec);
                  framesThisSec = 0;
                  lastFpsTime = now;
                }
              }
            },
            'image/jpeg',
            0.65
          );
        }
      }, 35); // Smooth 28-30 FPS transmission
    } catch (err: any) {
      setIsStreaming(false);
      setStreamingCamId(null);
      setStreamError(err.message || 'Camera permission denied');
    }
  };

  const stopDeviceStream = () => {
    if (streamTimerRef.current) {
      clearInterval(streamTimerRef.current);
      streamTimerRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {}
      wsRef.current = null;
    }
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((t) => t.stop());
      localStreamRef.current = null;
    }
    setIsStreaming(false);
    setStreamingCamId(null);
    setStreamFps(0);
  };

  const toggleFacingMode = () => {
    const nextMode = facingMode === 'environment' ? 'user' : 'environment';
    setFacingMode(nextMode);
    if (isStreaming && streamingCamId) {
      startDeviceStream(streamingCamId, nextMode);
    }
  };


  const handleAddCamera = async () => {
    const camId = newCamId.trim() || `cam${cameras.length}`;
    if (!camId) return;

    setIsAdding(true);
    setAddMessage(null);
    try {
      const res = await api.addCamera({
        camera_id: camId,
        source_type: newCamType,
        display_name: newCamName.trim() || undefined,
        url: newCamType === 'ip_camera' ? newCamUrl.trim() : undefined,
        device_index: newCamType === 'webcam' ? newCamIndex : undefined,
      });
      if (res.success) {
        setAddMessage({ type: 'success', text: `Camera "${camId}" added successfully!` });
        setNewCamId('');
        setNewCamName('');
        setNewCamUrl('');
        setGridKey(Date.now());
        await refreshData();
        setShowAddModal(false);

        // If user added mobile camera and wants to stream from this device right now:
        if (newCamType === 'mobile_browser' && autoStartStream) {
          setTimeout(() => {
            startDeviceStream(camId);
          }, 300);
        }
      } else {
        setAddMessage({ type: 'error', text: res.error || 'Failed to add camera' });
      }
    } catch (err: any) {
      setAddMessage({ type: 'error', text: err.message || 'Connection error' });
    } finally {
      setIsAdding(false);
    }
  };

  const handleRemoveCamera = async (cameraId: string) => {
    try {
      if (streamingCamId === cameraId) {
        stopDeviceStream();
      }
      await api.removeCamera(cameraId);
      refreshData();
      setGridKey(Date.now());
    } catch {
      // ignore
    }
  };

  const formatDwell = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    return `${(seconds / 60).toFixed(1)}m`;
  };

  const getTimeSince = (epochSec: number) => {
    const delta = Date.now() / 1000 - epochSec;
    if (delta < 60) return `${delta.toFixed(0)}s ago`;
    return `${(delta / 60).toFixed(0)}m ago`;
  };

  const activeFeedUrl = viewMode === 'grid'
    ? `${API_BASE}/api/video/feed/grid?t=${gridKey}`
    : `${API_BASE}/api/video/feed?camera_id=${viewMode}&t=${gridKey}`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Hidden local video element for frame capture */}
      <video
        ref={localVideoRef}
        playsInline
        muted
        autoPlay
        style={{ display: showLocalPreview ? 'block' : 'none', position: 'fixed', bottom: '16px', right: '16px', width: '160px', height: '120px', objectFit: 'cover', borderRadius: '8px', border: '2px solid var(--accent-emerald)', zIndex: 999 }}
      />

      {/* Header */}
      <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            width: '12px', height: '12px', borderRadius: '50%',
            background: cameras.length > 0 ? 'var(--accent-emerald)' : 'var(--accent-amber)',
            boxShadow: `0 0 12px ${cameras.length > 0 ? 'var(--accent-emerald)' : 'var(--accent-amber)'}`,
            animation: 'pulse-ring 1.5s infinite',
          }} />
          <div>
            <h3 style={{ fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              Multi-Camera Surveillance Grid
              <span className="chip-tag" style={{
                background: 'rgba(139, 92, 246, 0.15)',
                borderColor: 'rgba(139, 92, 246, 0.4)',
                color: '#a78bfa',
                fontSize: '0.72rem',
              }}>
                Cross-Camera Re-ID
              </span>
              <span className="chip-tag" style={{
                background: 'rgba(6, 182, 212, 0.12)',
                borderColor: 'rgba(6, 182, 212, 0.3)',
                color: 'var(--accent-cyan)',
                fontSize: '0.72rem',
              }}>
                {cameras.length} Camera{cameras.length !== 1 ? 's' : ''} Active
              </span>
            </h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Global Tracks: <strong style={{ color: 'var(--accent-amber)' }}>{globalTracks.length}</strong> unique individuals across all cameras
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={() => setShowAddModal(true)}
            className="btn-primary"
            style={{ padding: '6px 14px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
          >
            ➕ Add Camera
          </button>
          <button
            onClick={() => setGridKey(Date.now())}
            className="btn-secondary"
            style={{ padding: '6px 12px', fontSize: '0.75rem' }}
          >
            ↻ Refresh Grid
          </button>
        </div>
      </div>

      {/* Active Device Streaming Controller Banner */}
      {isStreaming && streamingCamId && (
        <div className="glass-panel animate-fade-in" style={{
          padding: '0.9rem 1.25rem',
          background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.18) 0%, rgba(6, 182, 212, 0.12) 100%)',
          border: '1px solid var(--accent-emerald)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{
              width: '12px', height: '12px', borderRadius: '50%',
              background: 'var(--accent-emerald)',
              boxShadow: '0 0 10px var(--accent-emerald)',
              animation: 'pulse-ring 1s infinite',
            }} />
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                📱 Streaming Phone Camera into <span style={{ color: 'var(--accent-emerald)', fontFamily: 'var(--font-mono)' }}>{streamingCamId}</span>
                <span className="chip-tag" style={{ background: 'rgba(16,185,129,0.25)', color: 'var(--accent-emerald)', fontSize: '0.72rem' }}>
                  {streamFps} FPS Live
                </span>
              </div>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                Active Lens: <strong>{facingMode === 'environment' ? 'Rear (World) Camera' : 'Front (Selfie) Camera'}</strong> • Frames streaming to Qualcomm Edge Hub
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              onClick={toggleFacingMode}
              className="btn-secondary"
              style={{ padding: '6px 12px', fontSize: '0.75rem' }}
              title="Flip camera between front and back"
            >
              🔄 Flip Lens
            </button>
            <button
              onClick={() => setShowLocalPreview(!showLocalPreview)}
              className="btn-secondary"
              style={{ padding: '6px 12px', fontSize: '0.75rem' }}
            >
              {showLocalPreview ? 'Hide Mini-PIP' : 'Show Mini-PIP'}
            </button>
            <button
              onClick={stopDeviceStream}
              className="btn-danger"
              style={{ padding: '6px 14px', fontSize: '0.75rem' }}
            >
              ⏹ Stop Stream
            </button>
          </div>
        </div>
      )}

      {/* Error alert if camera streaming failed */}
      {streamError && (
        <div className="glass-panel" style={{
          padding: '0.75rem 1rem',
          background: 'rgba(244, 63, 94, 0.12)',
          border: '1px solid var(--accent-rose)',
          color: 'var(--accent-rose)',
          fontSize: '0.8rem',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div>⚠️ {streamError}</div>
          <button onClick={() => setStreamError(null)} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>✕</button>
        </div>
      )}

      {/* Add Camera Modal */}
      {showAddModal && (
        <div className="glass-panel animate-fade-in" style={{
          padding: '1.25rem',
          border: '1px solid var(--accent-cyan)',
          display: 'flex', flexDirection: 'column', gap: '1rem',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h4 style={{ fontSize: '0.95rem' }}>📷 Register New Camera Source</h4>
            <button onClick={() => setShowAddModal(false)} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1rem' }}>✕</button>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 180px' }}>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Camera ID</label>
              <input
                type="text"
                placeholder={`cam${cameras.length}`}
                value={newCamId}
                onChange={e => setNewCamId(e.target.value)}
                style={inputStyle}
              />
            </div>
            <div style={{ flex: '1 1 200px' }}>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Display Name</label>
              <input
                type="text"
                placeholder="e.g. Store Entrance"
                value={newCamName}
                onChange={e => setNewCamName(e.target.value)}
                style={inputStyle}
              />
            </div>
          </div>

          {/* Source type selector */}
          <div style={{ display: 'flex', gap: '0.4rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem' }}>
            {(['mobile_browser', 'ip_camera', 'webcam'] as const).map(t => (
              <button
                key={t}
                onClick={() => setNewCamType(t)}
                className={`role-tab-btn ${newCamType === t ? 'active' : ''}`}
                style={{ padding: '4px 10px', fontSize: '0.75rem' }}
              >
                {t === 'mobile_browser' ? '📱 Mobile Device / Browser' : t === 'ip_camera' ? '🌐 Network IP Camera' : '💻 USB / Laptop Webcam'}
              </button>
            ))}
          </div>

          {newCamType === 'mobile_browser' && (
            <div style={{
              background: 'rgba(6, 182, 212, 0.08)',
              border: '1px solid rgba(6, 182, 212, 0.3)',
              borderRadius: '8px', padding: '0.75rem', fontSize: '0.75rem',
              display: 'flex', flexDirection: 'column', gap: '0.5rem',
            }}>
              <p style={{ color: 'var(--text-primary)', margin: 0 }}>
                📱 <strong>In-Browser Wireless Streaming:</strong> No app download needed!
              </p>
              <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                This device's camera will be accessed directly via the browser and stream frames to the server in real-time.
              </p>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '4px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={autoStartStream}
                  onChange={e => setAutoStartStream(e.target.checked)}
                />
                <span style={{ color: 'var(--accent-cyan)', fontWeight: 500 }}>
                  Start streaming from this device immediately after adding
                </span>
              </label>
            </div>
          )}

          {newCamType === 'ip_camera' && (
            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                Stream URL (RTSP / HTTP MJPEG)
              </label>
              <input
                type="text"
                placeholder="http://192.168.1.xx:8080/video"
                value={newCamUrl}
                onChange={e => setNewCamUrl(e.target.value)}
                style={{ ...inputStyle, width: '100%' }}
              />
              <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                💡 Tip: If using the Android "IP Webcam" app, enter: <code>http://&lt;phone-ip&gt;:8080/video</code>
              </p>
            </div>
          )}

          {newCamType === 'webcam' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>Webcam Device</label>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={() => { setNewCamIndex(1); if (!newCamName) setNewCamName('USB External Webcam'); }}
                  className="btn-secondary"
                  style={{
                    padding: '4px 10px',
                    fontSize: '0.72rem',
                    border: newCamIndex === 1 ? '1px solid var(--accent-emerald)' : undefined,
                    color: newCamIndex === 1 ? 'var(--accent-emerald)' : undefined,
                  }}
                >
                  🔌 USB External Webcam (1)
                </button>
                <button
                  type="button"
                  onClick={() => { setNewCamIndex(0); if (!newCamName) setNewCamName('Laptop Webcam'); }}
                  className="btn-secondary"
                  style={{
                    padding: '4px 10px',
                    fontSize: '0.72rem',
                    border: newCamIndex === 0 ? '1px solid var(--accent-cyan)' : undefined,
                    color: newCamIndex === 0 ? 'var(--accent-cyan)' : undefined,
                  }}
                >
                  💻 Laptop Built-in (0)
                </button>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '2px' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Custom Index:</span>
                <input
                  type="number"
                  value={newCamIndex}
                  onChange={e => setNewCamIndex(parseInt(e.target.value) || 0)}
                  style={{ ...inputStyle, width: '70px', padding: '3px 8px' }}
                  min={0}
                  max={10}
                />
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              onClick={handleAddCamera}
              disabled={isAdding}
              className="btn-primary"
              style={{ padding: '6px 16px', fontSize: '0.8rem' }}
            >
              {isAdding ? 'Connecting...' : '✓ Add & Start Camera'}
            </button>
          </div>

          {addMessage && (
            <div style={{
              fontSize: '0.75rem', padding: '6px 10px', borderRadius: '6px',
              background: addMessage.type === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              border: `1px solid ${addMessage.type === 'success' ? 'var(--accent-emerald)' : 'var(--accent-rose)'}`,
              color: addMessage.type === 'success' ? 'var(--accent-emerald)' : 'var(--accent-rose)',
            }}>
              {addMessage.text}
            </div>
          )}
        </div>
      )}

      {/* Main Content: Grid Feed + Global Tracker Side Panel */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '1rem', alignItems: 'start' }}>
        {/* Composite Grid or Focused Camera Video Feed */}
        <div className="glass-panel" style={{ padding: '1rem' }}>
          {/* Quick View Mode Switcher Ribbon */}
          <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, marginRight: '4px' }}>
              ⚡ VIEW:
            </span>
            <button
              onClick={() => { setViewMode('grid'); setGridKey(Date.now()); }}
              className={`role-tab-btn ${viewMode === 'grid' ? 'active' : ''}`}
              style={{ padding: '4px 12px', fontSize: '0.75rem' }}
            >
              ⊞ All Cameras Grid
            </button>
            {cameras.map(cam => {
              const isSelected = viewMode === cam.camera_id;
              return (
                <button
                  key={cam.camera_id}
                  onClick={() => { setViewMode(cam.camera_id); setGridKey(Date.now()); }}
                  className={`role-tab-btn ${isSelected ? 'active' : ''}`}
                  style={{
                    padding: '4px 10px',
                    fontSize: '0.75rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.4rem',
                  }}
                >
                  <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: cam.running ? 'var(--accent-emerald)' : 'var(--accent-rose)', display: 'inline-block' }} />
                  🔍 {cam.camera_id}
                </button>
              );
            })}
          </div>

          <div style={{
            position: 'relative', width: '100%', aspectRatio: '16 / 9',
            backgroundColor: '#000', borderRadius: '10px', overflow: 'hidden',
            border: '1px solid var(--border-subtle)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
          }}>
            <img
              src={activeFeedUrl}
              alt={viewMode === 'grid' ? 'Multi-Camera Grid Feed' : `Focused ${viewMode} Feed`}
              style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
              onError={() => setTimeout(() => setGridKey(Date.now()), 2000)}
            />
            <div style={{
              position: 'absolute', top: '8px', right: '10px',
              fontSize: '0.7rem', color: 'rgba(255,255,255,0.85)',
              background: 'rgba(0,0,0,0.65)', padding: '3px 10px',
              borderRadius: '4px', backdropFilter: 'blur(4px)',
            }}>
              {viewMode === 'grid' ? `${cameras.length} Cameras • Re-ID Active` : `FOCUSED VIEW: ${viewMode.toUpperCase()}`}
            </div>
          </div>

          {/* Per-camera status badges + Stream Trigger */}
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
            {cameras.map(cam => {
              const isCamStreamingFromHere = streamingCamId === cam.camera_id && isStreaming;
              const isMobileCam = cam.source_type === 'mobile_browser';
              const isFocused = viewMode === cam.camera_id;

              return (
                <div
                  key={cam.camera_id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                    background: isFocused ? 'rgba(6, 182, 212, 0.15)' : isCamStreamingFromHere ? 'rgba(16,185,129,0.1)' : 'rgba(0,0,0,0.4)',
                    border: `1px solid ${isFocused ? 'var(--accent-cyan)' : isCamStreamingFromHere ? 'var(--accent-emerald)' : 'var(--border-subtle)'}`,
                    borderRadius: '8px', padding: '6px 10px', fontSize: '0.72rem', flexWrap: 'wrap',
                  }}
                >
                  <span style={{
                    width: '7px', height: '7px', borderRadius: '50%',
                    background: cam.running ? 'var(--accent-emerald)' : 'var(--accent-rose)',
                    display: 'inline-block',
                  }} />
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{cam.camera_id}</span>
                  <span style={{ color: 'var(--text-muted)' }}>
                    {cam.display_name} •
                    {cam.source_type === 'ip_camera' ? ' 🌐' : cam.source_type === 'mobile_browser' ? ' 📱' : ' 💻'}
                  </span>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {cam.tracks_count} tracks • {cam.fps} FPS
                  </span>

                  {/* Switch to Focused Single-Cam Feed */}
                  <button
                    onClick={() => { setViewMode(isFocused ? 'grid' : cam.camera_id); setGridKey(Date.now()); }}
                    style={{
                      background: isFocused ? 'rgba(6,182,212,0.25)' : 'rgba(255,255,255,0.08)',
                      border: '1px solid var(--border-subtle)',
                      color: isFocused ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                      borderRadius: '4px', padding: '2px 7px', fontSize: '0.68rem', cursor: 'pointer',
                    }}
                    title="Toggle focused full-screen view for this camera"
                  >
                    {isFocused ? '⊞ Grid' : '🔍 Focus'}
                  </button>

                  {/* One-tap Start Streaming Button for mobile cameras */}
                  {isMobileCam && (
                    isCamStreamingFromHere ? (
                      <span style={{ color: 'var(--accent-emerald)', fontWeight: 600, fontSize: '0.68rem', background: 'rgba(16,185,129,0.2)', padding: '2px 6px', borderRadius: '4px' }}>
                        ● Streaming Live
                      </span>
                    ) : (
                      <button
                        onClick={() => startDeviceStream(cam.camera_id)}
                        className="btn-primary"
                        style={{ padding: '2px 8px', fontSize: '0.68rem', borderRadius: '4px' }}
                        title="Start capturing and streaming this device's camera to this camera slot"
                      >
                        📱 Stream This Device
                      </button>
                    )
                  )}

                  {cam.camera_id !== 'cam0' && (
                    <button
                      onClick={() => handleRemoveCamera(cam.camera_id)}
                      style={{
                        background: 'rgba(244,63,94,0.15)', border: '1px solid var(--accent-rose)',
                        color: 'var(--accent-rose)', borderRadius: '4px', padding: '1px 6px',
                        fontSize: '0.68rem', cursor: 'pointer',
                      }}
                      title="Remove Camera"
                    >
                      ✕
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>


        {/* Global Re-ID Tracker Panel */}
        <div className="glass-panel" style={{ padding: '1rem', maxHeight: '600px', overflowY: 'auto' }}>
          <h4 style={{
            fontSize: '0.9rem', marginBottom: '0.75rem',
            display: 'flex', alignItems: 'center', gap: '0.5rem',
            borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem',
          }}>
            <span style={{
              width: '8px', height: '8px', borderRadius: '50%',
              background: 'var(--accent-amber)',
              boxShadow: '0 0 10px var(--accent-amber)',
              display: 'inline-block',
            }} />
            Global Person Registry
            <span className="chip-tag" style={{
              fontSize: '0.68rem',
              background: 'rgba(251,191,36,0.12)',
              borderColor: 'rgba(251,191,36,0.3)',
              color: 'var(--accent-amber)',
            }}>
              {globalTracks.length} unique
            </span>
          </h4>

          {globalTracks.length === 0 ? (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
              No persons tracked yet. Waiting for detections across cameras...
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {globalTracks.map(track => (
                <div
                  key={track.global_id}
                  style={{
                    background: track.total_cameras > 1
                      ? 'linear-gradient(135deg, rgba(139,92,246,0.12) 0%, rgba(6,182,212,0.08) 100%)'
                      : 'rgba(0,0,0,0.3)',
                    border: `1px solid ${track.total_cameras > 1 ? 'rgba(139,92,246,0.4)' : 'var(--border-subtle)'}`,
                    borderRadius: '8px', padding: '8px 10px',
                    transition: 'all 0.3s ease',
                  }}
                >
                  {/* Top row: Global ID + Gender */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span style={{
                        fontSize: '0.85rem', fontWeight: 700,
                        color: track.total_cameras > 1 ? '#a78bfa' : 'var(--accent-cyan)',
                        fontFamily: 'var(--font-mono)',
                      }}>
                        G#{track.global_id}
                      </span>
                      <span style={{
                        fontSize: '0.68rem', padding: '1px 6px',
                        borderRadius: '4px',
                        background: track.gender === 'Male' ? 'rgba(59,130,246,0.15)' : 'rgba(244,114,182,0.15)',
                        color: track.gender === 'Male' ? '#60a5fa' : '#f472b6',
                        border: `1px solid ${track.gender === 'Male' ? 'rgba(59,130,246,0.3)' : 'rgba(244,114,182,0.3)'}`,
                      }}>
                        {track.gender} ({(track.gender_confidence * 100).toFixed(0)}%)
                      </span>
                    </div>
                    <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                      {formatDwell(track.dwell_time_s)}
                    </span>
                  </div>

                  {/* Camera journey */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', flexWrap: 'wrap' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Seen on:</span>
                    {track.cameras_visited.map((camId, i) => (
                      <React.Fragment key={camId}>
                        {i > 0 && <span style={{ color: 'var(--accent-amber)' }}>→</span>}
                        <span style={{
                          padding: '1px 5px', borderRadius: '3px',
                          background: camId === track.camera_id ? 'rgba(16,185,129,0.2)' : 'rgba(255,255,255,0.06)',
                          border: `1px solid ${camId === track.camera_id ? 'var(--accent-emerald)' : 'var(--border-subtle)'}`,
                          color: camId === track.camera_id ? 'var(--accent-emerald)' : 'var(--text-secondary)',
                          fontFamily: 'var(--font-mono)',
                        }}>
                          {camId}
                        </span>
                      </React.Fragment>
                    ))}
                    {track.total_cameras > 1 && (
                      <span style={{
                        fontSize: '0.65rem', color: '#a78bfa',
                        marginLeft: '0.25rem', fontWeight: 600,
                      }}>
                        🔗 Re-ID Match
                      </span>
                    )}
                  </div>

                  {/* Last seen */}
                  <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '3px' }}>
                    Now on <strong style={{ color: 'var(--accent-cyan)' }}>{track.camera_id}</strong> •
                    Local ID #{track.local_track_id} •
                    Last: {getTimeSince(track.last_seen_time)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const inputStyle: React.CSSProperties = {
  padding: '6px 10px',
  fontSize: '0.8rem',
  background: 'rgba(0,0,0,0.4)',
  border: '1px solid var(--border-subtle)',
  borderRadius: '6px',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-mono)',
  width: '100%',
};

