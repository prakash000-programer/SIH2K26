import React, { useState, useEffect, useRef } from 'react';
import { API_BASE, api } from '../../api/client';

interface LiveCameraFeedProps {
  compact?: boolean;
  onSnapshot?: () => void;
}

export const LiveCameraFeed: React.FC<LiveCameraFeedProps> = ({ compact = false }) => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [status, setStatus] = useState<{
    active: boolean;
    fps: number;
    tracks_count: number;
    is_high_density: boolean;
    source_name?: string;
    source_type?: string;
  }>({
    active: true,
    fps: 30.0,
    tracks_count: 0,
    is_high_density: false,
    source_name: 'Laptop Webcam',
    source_type: 'webcam',
  });

  const [activeCameraId, setActiveCameraId] = useState<string>('cam0');
  const [cameraList, setCameraList] = useState<any[]>([]);

  // Camera Source Switcher Modal state
  const [showSourceModal, setShowSourceModal] = useState(false);
  const [selectedTab, setSelectedTab] = useState<'browser_stream' | 'ip_camera' | 'webcam'>('browser_stream');
  const [ipCamUrl, setIpCamUrl] = useState('');
  const [isSwitching, setIsSwitching] = useState(false);
  const [switchMessage, setSwitchMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // In-browser mobile camera streaming state
  const [isStreamingPhone, setIsStreamingPhone] = useState(false);
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment');
  const [phoneFps, setPhoneFps] = useState(0);

  const localVideoRef = useRef<HTMLVideoElement | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const streamTimerRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const isUploadingRef = useRef(false);
  const frameCountRef = useRef(0);

  const feedUrl = `${API_BASE}/api/video/feed?camera_id=${activeCameraId}&t=${streamKey}`;

  // Poll camera status & list periodically
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [res, camRes] = await Promise.all([
          fetch(`${API_BASE}/api/video/status`),
          api.listCameras().catch(() => ({ cameras: [] })),
        ]);
        if (res.ok) {
          const data = await res.json();
          setStatus(data);
        }
        if (camRes && camRes.cameras && camRes.cameras.length > 0) {
          setCameraList(camRes.cameras);
        }
      } catch {
        // ignore offline polls
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // Cleanup phone camera on unmount
  useEffect(() => {
    return () => {
      stopPhoneCamera();
    };
  }, []);

  const handleRefreshStream = () => {
    setStreamKey(Date.now());
  };

  const handleDownloadSnapshot = () => {
    window.open(`${API_BASE}/api/video/snapshot?camera_id=${activeCameraId}&download=1`, '_blank');
  };

  // --- Phone Camera Streaming via Browser (Ultra-fast WebSocket / getUserMedia) ---
  const startPhoneCamera = async () => {
    try {
      setSwitchMessage(null);
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        const secureUrl = `https://${window.location.host}`;
        throw new Error(
          `Mobile browsers strictly block camera access on plain HTTP. Please open this page via HTTPS: ${secureUrl} (tap 'Advanced' -> 'Proceed to site') or use Tab 2: Network IP Camera App.`
        );
      }

      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach((t) => t.stop());
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: facingMode },
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

      // Connect low-latency binary WebSocket for zero HTTP header overhead
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api/video/ws-stream-in?camera_id=${activeCameraId}`;
      try {
        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'blob';
        wsRef.current = ws;
      } catch {
        wsRef.current = null;
      }

      setIsStreamingPhone(true);
      frameCountRef.current = 0;

      // Start frame capture loop (~25-30 FPS)
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
                  fetch(`${API_BASE}/api/video/ingest-frame?camera_id=${activeCameraId}`, {
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
                  setPhoneFps(framesThisSec);
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

      setSwitchMessage({
        type: 'success',
        text: 'Phone camera is live! Streaming frames at ~30 FPS over low-latency socket.',
      });
    } catch (err: any) {
      setIsStreamingPhone(false);
      setSwitchMessage({
        type: 'error',
        text: `Camera permission denied or camera unavailable: ${err.message || err}`,
      });
    }
  };

  const stopPhoneCamera = () => {
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
    setIsStreamingPhone(false);
    setPhoneFps(0);
  };


  const toggleFacingMode = () => {
    const nextMode = facingMode === 'environment' ? 'user' : 'environment';
    setFacingMode(nextMode);
    if (isStreamingPhone) {
      setTimeout(() => startPhoneCamera(), 200);
    }
  };

  // --- Switch to IP Camera (IP Webcam / DroidCam app URL) ---
  const handleConnectIpCamera = async () => {
    if (!ipCamUrl.trim()) {
      setSwitchMessage({ type: 'error', text: 'Please enter a stream URL (e.g. http://172.20.66.xxx:8080/video)' });
      return;
    }

    setIsSwitching(true);
    setSwitchMessage(null);
    try {
      const res = await api.switchCameraSource({
        source_type: 'ip_camera',
        url: ipCamUrl.trim(),
      });
      if (res.success) {
        setSwitchMessage({ type: 'success', text: `Connected to Network Camera: ${res.source_name}` });
        handleRefreshStream();
      } else {
        setSwitchMessage({ type: 'error', text: res.error || 'Could not connect to IP camera' });
      }
    } catch (err: any) {
      setSwitchMessage({ type: 'error', text: `Connection failed: ${err.message || err}` });
    } finally {
      setIsSwitching(false);
    }
  };

  // --- Switch to Local Webcam (USB or Built-in) ---
  const handleSwitchToWebcam = async (deviceIndex: number = 1) => {
    setIsSwitching(true);
    setSwitchMessage(null);
    stopPhoneCamera();
    try {
      const res = await api.switchCameraSource({
        source_type: 'webcam',
        device_index: deviceIndex,
      });
      if (res.success) {
        setSwitchMessage({
          type: 'success',
          text: `Switched to ${deviceIndex === 1 ? 'External USB Webcam (1)' : `Webcam (${deviceIndex})`}.`,
        });
        handleRefreshStream();
      } else {
        setSwitchMessage({ type: 'error', text: res.error || `Could not open webcam at index ${deviceIndex}` });
      }
    } catch (err: any) {
      setSwitchMessage({ type: 'error', text: `Switch failed: ${err.message || err}` });
    } finally {
      setIsSwitching(false);
    }
  };

  return (
    <div
      className={`glass-panel ${isFullscreen ? 'fullscreen-feed' : ''}`}
      style={{
        padding: compact ? '1rem' : '1.5rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        position: isFullscreen ? 'fixed' : 'relative',
        top: isFullscreen ? 0 : undefined,
        left: isFullscreen ? 0 : undefined,
        right: isFullscreen ? 0 : undefined,
        bottom: isFullscreen ? 0 : undefined,
        zIndex: isFullscreen ? 9999 : 10,
        backgroundColor: isFullscreen ? 'rgba(7, 10, 19, 0.98)' : undefined,
      }}
    >
      {/* Header Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: status.active ? 'var(--accent-emerald)' : 'var(--accent-rose)',
              boxShadow: `0 0 12px ${status.active ? 'var(--accent-emerald)' : 'var(--accent-rose)'}`,
              animation: 'pulse-ring 1.5s infinite',
            }}
          />
          <div>
            <h3 style={{ fontSize: compact ? '1rem' : '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              Live Camera Vision Stream
              <span className="chip-tag" style={{ background: 'rgba(16, 185, 129, 0.15)', borderColor: 'rgba(16, 185, 129, 0.4)', color: 'var(--accent-emerald)' }}>
                YOLOv8 + ByteTrack
              </span>
              <span
                className="chip-tag"
                style={{
                  background: status.source_type === 'mobile_browser' || status.source_type === 'ip_camera' ? 'rgba(6, 182, 212, 0.15)' : 'rgba(255, 255, 255, 0.08)',
                  borderColor: status.source_type === 'mobile_browser' || status.source_type === 'ip_camera' ? 'var(--accent-cyan)' : 'var(--border-subtle)',
                  color: status.source_type === 'mobile_browser' || status.source_type === 'ip_camera' ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                  fontSize: '0.7rem',
                }}
              >
                {status.source_type === 'mobile_browser' ? '📱 Mobile Phone Stream' : status.source_type === 'ip_camera' ? '🌐 IP Camera' : '💻 PC Webcam'}
              </span>
            </h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Source: <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{status.source_name || 'Webcam 0'}</span>
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span
            style={{
              fontSize: '0.75rem',
              color: 'var(--text-secondary)',
              background: 'rgba(7, 10, 19, 0.6)',
              padding: '4px 8px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {status.tracks_count} {status.tracks_count === 1 ? 'Shopper' : 'Shoppers'} Detected
          </span>

          {/* Camera Source Switcher Trigger Button */}
          <button
            onClick={() => setShowSourceModal(!showSourceModal)}
            className="btn-primary"
            style={{
              padding: '4px 12px',
              fontSize: '0.78rem',
              background: isStreamingPhone ? 'var(--accent-emerald)' : 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
              boxShadow: isStreamingPhone ? '0 0 14px rgba(16, 185, 129, 0.4)' : undefined,
            }}
            title="Switch camera source to mobile phone or network camera"
          >
            📱 {isStreamingPhone ? 'Phone Streaming (Active)' : 'Switch to Phone Camera'}
          </button>

          <button
            onClick={handleDownloadSnapshot}
            className="btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            title="Download current high-res annotated frame"
          >
            📷 Snapshot
          </button>

          <button
            onClick={handleRefreshStream}
            className="btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            title="Reconnect / reload video feed"
          >
            ↻ Reconnect
          </button>

          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
          >
            {isFullscreen ? '✕ Exit' : '⛶ Fullscreen'}
          </button>
        </div>
      </div>

      {/* Camera Switcher Modal / Tray */}
      {showSourceModal && (
        <div
          className="animate-fade-in"
          style={{
            background: 'rgba(10, 15, 26, 0.95)',
            borderRadius: '10px',
            border: '1px solid var(--accent-cyan)',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h4 style={{ fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                📷 Select Video Input Source
              </h4>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                Switch input seamlessly from laptop webcam to your mobile phone camera over the Wi-Fi network
              </p>
            </div>
            <button
              onClick={() => setShowSourceModal(false)}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1rem' }}
            >
              ✕
            </button>
          </div>

          {/* Navigation Tabs */}
          <div style={{ display: 'flex', gap: '0.4rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem' }}>
            <button
              onClick={() => setSelectedTab('browser_stream')}
              className={`role-tab-btn ${selectedTab === 'browser_stream' ? 'active' : ''}`}
              style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            >
              📱 Phone Browser Camera (Zero-Install)
            </button>
            <button
              onClick={() => setSelectedTab('ip_camera')}
              className={`role-tab-btn ${selectedTab === 'ip_camera' ? 'active' : ''}`}
              style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            >
              🌐 Network IP Camera App (IP Webcam / DroidCam)
            </button>
            <button
              onClick={() => setSelectedTab('webcam')}
              className={`role-tab-btn ${selectedTab === 'webcam' ? 'active' : ''}`}
              style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            >
              🔌 USB / Laptop Webcam
            </button>
          </div>

          {/* Tab 1: Direct Mobile Browser Streaming */}
          {selectedTab === 'browser_stream' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ background: 'rgba(6, 182, 212, 0.08)', border: '1px solid rgba(6, 182, 212, 0.3)', borderRadius: '8px', padding: '0.75rem', fontSize: '0.75rem', lineHeight: '1.4' }}>
                <p>
                  <strong>How to use your phone as a smart camera:</strong>
                </p>
                <ol style={{ paddingLeft: '1.2rem', marginTop: '0.25rem' }}>
                  <li>Open via <strong>HTTPS</strong> on your mobile browser: <code style={{ color: 'var(--accent-cyan)', background: 'rgba(0,0,0,0.4)', padding: '2px 6px', borderRadius: '4px' }}>https://{typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:3000</code></li>
                  <li>Tap <strong>"Advanced" → "Proceed to site"</strong> to accept the local dev SSL certificate.</li>
                  <li>Tap <strong>"Start Broadcasting Phone Camera"</strong> below and tap Allow!</li>
                </ol>
                <p style={{ marginTop: '0.4rem', color: 'var(--accent-amber)', fontSize: '0.7rem' }}>
                  💡 <em>Prefer not using HTTPS? Switch to <strong>Tab 2 (Network IP Camera App)</strong> to connect via the free "IP Webcam" app.</em>
                </p>
              </div>

              {/* Local Phone Camera Controls */}
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
                {!isStreamingPhone ? (
                  <button
                    onClick={startPhoneCamera}
                    className="btn-primary"
                    style={{ padding: '6px 14px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                  >
                    📹 Start Broadcasting Phone Camera
                  </button>
                ) : (
                  <button
                    onClick={stopPhoneCamera}
                    className="btn-secondary"
                    style={{ padding: '6px 14px', fontSize: '0.8rem', borderColor: 'var(--accent-rose)', color: 'var(--accent-rose)' }}
                  >
                    ⏹ Stop Phone Broadcast
                  </button>
                )}

                <button
                  onClick={toggleFacingMode}
                  className="btn-secondary"
                  style={{ padding: '6px 12px', fontSize: '0.75rem' }}
                  title="Switch between back (environment) and front (user) cameras"
                >
                  🔄 Flip: {facingMode === 'environment' ? 'Rear (Back) Camera' : 'Front Camera'}
                </button>

                {isStreamingPhone && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--accent-emerald)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--accent-emerald)', display: 'inline-block', animation: 'pulse-ring 1s infinite' }} />
                    Broadcasting at ~{phoneFps} FPS
                  </span>
                )}
              </div>

              {/* Hidden/Thumbnail Preview for phone */}
              <div style={{ display: isStreamingPhone ? 'block' : 'none' }}>
                <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Local Phone Sensor View:</p>
                <video
                  ref={localVideoRef}
                  playsInline
                  muted
                  style={{ width: '160px', height: '120px', borderRadius: '6px', objectFit: 'cover', border: '1px solid var(--accent-cyan)' }}
                />
              </div>
            </div>
          )}

          {/* Tab 2: IP Camera URL App */}
          {selectedTab === 'ip_camera' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                If you use mobile apps like <strong>IP Webcam</strong> or <strong>DroidCam</strong> on Android/iOS, enter the stream URL:
              </p>

              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <input
                  type="text"
                  placeholder="e.g. http://172.20.66.xxx:8080/video"
                  value={ipCamUrl}
                  onChange={(e) => setIpCamUrl(e.target.value)}
                  style={{
                    flex: 1,
                    minWidth: '240px',
                    padding: '6px 10px',
                    fontSize: '0.8rem',
                    background: 'rgba(0, 0, 0, 0.4)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '6px',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-mono)',
                  }}
                />
                <button
                  onClick={handleConnectIpCamera}
                  disabled={isSwitching}
                  className="btn-primary"
                  style={{ padding: '6px 14px', fontSize: '0.78rem' }}
                >
                  {isSwitching ? 'Connecting...' : 'Connect Network Camera'}
                </button>
              </div>

              {/* Quick Presets */}
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', fontSize: '0.72rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Presets:</span>
                <button
                  onClick={() => setIpCamUrl('http://172.20.66.82:8080/video')}
                  className="btn-secondary"
                  style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                >
                  IP Webcam (:8080/video)
                </button>
                <button
                  onClick={() => setIpCamUrl('http://172.20.66.82:4747/video')}
                  className="btn-secondary"
                  style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                >
                  DroidCam (:4747/video)
                </button>
              </div>
            </div>
          )}

          {/* Tab 3: USB / Laptop Webcam */}
          {selectedTab === 'webcam' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Select a connected physical camera on this computer:
              </p>
              <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <button
                  onClick={() => handleSwitchToWebcam(1)}
                  disabled={isSwitching}
                  className="btn-primary"
                  style={{
                    padding: '8px 16px',
                    fontSize: '0.8rem',
                    background: 'linear-gradient(135deg, #10b981 0%, #06b6d4 100%)',
                    boxShadow: '0 0 14px rgba(16, 185, 129, 0.3)',
                  }}
                >
                  {isSwitching ? 'Switching...' : '🔌 USB External Webcam (Index 1)'}
                </button>
                <button
                  onClick={() => handleSwitchToWebcam(0)}
                  disabled={isSwitching}
                  className="btn-secondary"
                  style={{ padding: '8px 16px', fontSize: '0.8rem' }}
                >
                  {isSwitching ? 'Switching...' : '💻 Built-in Laptop Webcam (Index 0)'}
                </button>
              </div>
            </div>
          )}

          {/* Feedback message */}
          {switchMessage && (
            <div
              style={{
                fontSize: '0.75rem',
                padding: '6px 10px',
                borderRadius: '6px',
                background: switchMessage.type === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                border: `1px solid ${switchMessage.type === 'success' ? 'var(--accent-emerald)' : 'var(--accent-rose)'}`,
                color: switchMessage.type === 'success' ? 'var(--accent-emerald)' : 'var(--accent-rose)',
              }}
            >
              {switchMessage.text}
            </div>
          )}
        </div>
      )}

      {/* Instant Camera Switcher Ribbon */}
      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap', background: 'rgba(7, 10, 19, 0.7)', padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.3rem', marginRight: '4px' }}>
          ⚡ SWITCH CAMERA:
        </span>

        {/* Primary cam0 */}
        <button
          onClick={() => {
            setActiveCameraId('cam0');
            setStreamKey(Date.now());
          }}
          className={`role-tab-btn ${activeCameraId === 'cam0' ? 'active' : ''}`}
          style={{
            padding: '4px 10px',
            fontSize: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
          }}
        >
          <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: 'var(--accent-emerald)', display: 'inline-block' }} />
          <strong>cam0</strong>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>(💻 Default)</span>
        </button>

        {/* Other registered cameras */}
        {cameraList.filter(c => c.camera_id !== 'cam0').map(cam => {
          const isSelected = activeCameraId === cam.camera_id;
          return (
            <button
              key={cam.camera_id}
              onClick={() => {
                setActiveCameraId(cam.camera_id);
                setStreamKey(Date.now());
              }}
              className={`role-tab-btn ${isSelected ? 'active' : ''}`}
              style={{
                padding: '4px 10px',
                fontSize: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: cam.running ? 'var(--accent-emerald)' : 'var(--accent-rose)', display: 'inline-block' }} />
              <strong>{cam.camera_id}</strong>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>
                ({cam.source_type === 'mobile_browser' ? '📱' : cam.source_type === 'ip_camera' ? '🌐' : '💻'} {cam.display_name})
              </span>
              <span style={{ color: 'var(--accent-amber)', fontSize: '0.68rem', fontFamily: 'var(--font-mono)' }}>
                {cam.fps} FPS
              </span>
            </button>
          );
        })}

        <button
          onClick={() => setShowSourceModal(true)}
          style={{
            background: 'transparent',
            border: '1px dashed var(--border-subtle)',
            color: 'var(--accent-cyan)',
            padding: '3px 8px',
            borderRadius: '6px',
            fontSize: '0.72rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.3rem',
          }}
        >
          ➕ Connect Camera
        </button>
      </div>

      {/* Video Display Container */}
      <div
        style={{
          position: 'relative',

          width: '100%',
          aspectRatio: '16 / 10',
          maxHeight: isFullscreen ? 'calc(100vh - 120px)' : '480px',
          backgroundColor: '#000000',
          borderRadius: '12px',
          overflow: 'hidden',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)',
        }}
      >
        <img
          src={feedUrl}
          alt="Live Camera Tracking Feed"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            display: 'block',
          }}
          onError={() => {
            // If feed drops, try refreshing after 2s
            setTimeout(() => setStreamKey(Date.now()), 2000);
          }}
        />

        {/* Live HUD Corner Watermark */}
        <div
          style={{
            position: 'absolute',
            bottom: '10px',
            left: '12px',
            fontSize: '0.7rem',
            color: 'rgba(255, 255, 255, 0.75)',
            background: 'rgba(0, 0, 0, 0.6)',
            padding: '3px 8px',
            borderRadius: '4px',
            backdropFilter: 'blur(4px)',
            pointerEvents: 'none',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span style={{ color: 'var(--accent-cyan)', fontWeight: 700 }}>QUALCOMM QCS6490 TARGET</span>
          <span>•</span>
          <span>Zero Disk Storage</span>
          {status.source_name && (
            <>
              <span>•</span>
              <span style={{ color: 'var(--accent-emerald)' }}>{status.source_name}</span>
            </>
          )}
        </div>
      </div>

      {/* Footer Info Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
          borderTop: '1px solid var(--border-subtle)',
          paddingTop: '0.75rem',
          flexWrap: 'wrap',
          gap: '0.5rem',
        }}
      >
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span>
            Active Input: <strong style={{ color: 'var(--accent-cyan)' }}>{status.source_name || 'Webcam 0'}</strong>
          </span>
          <span>•</span>
          <span>
            Model: <strong style={{ color: 'var(--text-primary)' }}>YOLOv8n (Person Class 0)</strong>
          </span>
          <span>•</span>
          <span>
            Tracker: <strong style={{ color: 'var(--text-primary)' }}>ByteTrack (Ephemeral IDs)</strong>
          </span>
        </div>

        <div style={{ color: 'var(--accent-cyan)' }}>
          🔒 Privacy Compliant • Memory-Only RAM Processing
        </div>
      </div>
    </div>
  );
};
