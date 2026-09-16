import { useEffect, useRef, useState, useCallback } from 'react';
import type { UserRole, DetectionStreamData, AlertItem } from '../types';

interface UseWebSocketOptions {
  role: UserRole;
  onDetection?: (data: DetectionStreamData) => void;
  onFootfall?: (data: { direction: string; timestamp: number }) => void;
  onDwell?: (data: { zone_id: string; qualifying_time_s: number; timestamp: number }) => void;
  onQueueUpdate?: (data: { counter_id: string; queue_size: number; all_queues: Record<string, number> }) => void;
  onAlert?: (alert: AlertItem) => void;
}

export function useWebSocket({
  role,
  onDetection,
  onFootfall,
  onDwell,
  onQueueUpdate,
  onAlert,
}: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessageTime, setLastMessageTime] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  // Keep callback refs fresh
  const callbacksRef = useRef({ onDetection, onFootfall, onDwell, onQueueUpdate, onAlert });
  callbacksRef.current = { onDetection, onFootfall, onDwell, onQueueUpdate, onAlert };

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsProtocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = typeof window !== 'undefined' && window.location.host ? window.location.host : 'localhost:3000';
    const wsUrl = `${wsProtocol}//${wsHost}/ws?role=${role}`;
    try {
      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        setIsConnected(true);
      };

      socket.onmessage = (event) => {
        setLastMessageTime(Date.now());
        try {
          const payload = JSON.parse(event.data);
          const type = payload.type || payload.event;
          const data = payload.data || payload;

          if (type === 'detections' && callbacksRef.current.onDetection) {
            callbacksRef.current.onDetection(data);
          } else if (type === 'footfall' && callbacksRef.current.onFootfall) {
            callbacksRef.current.onFootfall(data);
          } else if (type === 'dwell' && callbacksRef.current.onDwell) {
            callbacksRef.current.onDwell(data);
          } else if (type === 'queue_update' && callbacksRef.current.onQueueUpdate) {
            callbacksRef.current.onQueueUpdate(data);
          } else if (type === 'queue_alert') {
            const alert: AlertItem = {
              id: `qa-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
              type: 'queue',
              title: 'Checkout Queue Alert',
              message: `Queue threshold exceeded! Predicted queue size: ${Number(data.predicted_queue || 0).toFixed(1)} (Max acceptable: ${Number(data.max_acceptable || 0).toFixed(1)}). Recommended: open additional counter.`,
              timestamp: Date.now(),
              details: data,
            };
            callbacksRef.current.onAlert?.(alert);
          } else if (type === 'stockout') {
            const alert: AlertItem = {
              id: `so-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
              type: 'stockout',
              title: 'Shelf Stock-Out Alert',
              message: `Shelf "${data.slot_name}" is empty after 3 consecutive scans. Diff ratio: ${(data.diff_ratio * 100).toFixed(1)}%. Immediate restock required.`,
              timestamp: Date.now(),
              details: data,
            };
            callbacksRef.current.onAlert?.(alert);
          } else if (type === 'crowd_alert') {
            const alert: AlertItem = {
              id: `ca-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
              type: 'density',
              title: 'High Crowd Density Alert',
              message: `High shopper density detected: ${data.total_persons} shoppers present in monitored zone.`,
              timestamp: Date.now(),
              details: data,
            };
            callbacksRef.current.onAlert?.(alert);
          }
        } catch {
          // ignore non-json ping/pongs
        }
      };

      socket.onclose = () => {
        setIsConnected(false);
        // Attempt reconnection after 3 seconds
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, 3000);
      };

      socket.onerror = () => {
        socket.close();
      };
    } catch {
      setIsConnected(false);
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 4000);
    }
  }, [role]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const send = (type: string, data: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...data }));
    }
  };

  return { isConnected, lastMessageTime, send };
}
