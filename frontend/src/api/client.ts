import type {
  HeatmapResponse,
  DwellResponse,
  FootfallResponse,
  ManagerSummary,
  QueuePrediction,
  QueueConfig,
  InventorySlot,
  ROIResponse,
  CalibrationStatus,
  GlobalTrack,
  CameraInfo,
} from '../types';

const getApiBase = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  return '';
};

export const API_BASE = getApiBase();

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API Error ${res.status}: ${errText}`);
  }
  return res.json();
}

export const api = {
  // Health
  getHealth: () => fetch(`${API_BASE}/api/health`).then(handleResponse<{ status: string; cv_available?: boolean }>),

  // Analytics
  getHeatmap: (start?: number, end?: number) => {
    const params = new URLSearchParams();
    if (start !== undefined) params.append('start', start.toString());
    if (end !== undefined) params.append('end', end.toString());
    return fetch(`${API_BASE}/api/analytics/heatmap?${params.toString()}`).then(handleResponse<HeatmapResponse>);
  },

  getDwell: (start?: number, end?: number, zone?: string) => {
    const params = new URLSearchParams();
    if (start !== undefined) params.append('start', start.toString());
    if (end !== undefined) params.append('end', end.toString());
    if (zone) params.append('zone', zone);
    return fetch(`${API_BASE}/api/analytics/dwell?${params.toString()}`).then(handleResponse<DwellResponse>);
  },

  getFootfall: (start?: number, end?: number) => {
    const params = new URLSearchParams();
    if (start !== undefined) params.append('start', start.toString());
    if (end !== undefined) params.append('end', end.toString());
    return fetch(`${API_BASE}/api/analytics/footfall?${params.toString()}`).then(handleResponse<FootfallResponse>);
  },

  // Dashboard & ROI
  getSummary: () => fetch(`${API_BASE}/api/dashboard/summary`).then(handleResponse<ManagerSummary>),

  calculateROI: (baselineRevenue: number) =>
    fetch(`${API_BASE}/api/dashboard/roi`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ baseline_monthly_revenue: baselineRevenue }),
    }).then(handleResponse<ROIResponse>),

  // Queue Intelligence
  getQueueStatus: () => fetch(`${API_BASE}/api/queue/status`).then(handleResponse<{ queues: Record<string, number> }>),

  getQueuePrediction: () => fetch(`${API_BASE}/api/queue/prediction`).then(handleResponse<QueuePrediction>),

  incrementQueue: (counterId: string) =>
    fetch(`${API_BASE}/api/queue/increment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ counter_id: counterId }),
    }).then(handleResponse<{ counter_id: string; queue_size: number }>),

  decrementQueue: (counterId: string) =>
    fetch(`${API_BASE}/api/queue/decrement`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ counter_id: counterId }),
    }).then(handleResponse<{ counter_id: string; queue_size: number }>),

  updateQueueConfig: (config: Partial<QueueConfig>) =>
    fetch(`${API_BASE}/api/queue/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }).then(handleResponse<{ success: boolean; config: QueueConfig }>),

  // Inventory
  getInventorySlots: () => fetch(`${API_BASE}/api/inventory/slots`).then(handleResponse<{ slots: InventorySlot[] }>),

  createSlot: (slotName: string, totalStock: number) =>
    fetch(`${API_BASE}/api/inventory/slots`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot_name: slotName, total_stock: totalStock }),
    }).then(handleResponse<{ slot_id: number; slot_name: string; total_stock: number }>),

  recordSale: (slotName: string, quantity: number) =>
    fetch(`${API_BASE}/api/inventory/sales`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot_name: slotName, quantity }),
    }).then(handleResponse<{ slot_name: string; quantity: number; status: string }>),

  checkShelf: (slotName: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${API_BASE}/api/inventory/slots/${encodeURIComponent(slotName)}/check`, {
      method: 'POST',
      body: formData,
    }).then(handleResponse<{ slot_name: string; diff_ratio: number; is_empty: boolean; stockout_fired: boolean }>);
  },

  // Calibration
  getCalibrationStatus: () =>
    fetch(`${API_BASE}/api/calibration/status`).then(handleResponse<CalibrationStatus>),

  setCalibrationPoints: (data: {
    pixel_points: [number, number][];
    world_points: [number, number][];
    floor_width_m: number;
    floor_height_m: number;
  }) =>
    fetch(`${API_BASE}/api/calibration/points`, {
      method: 'POST',
      body: JSON.stringify(data),
    }).then(handleResponse<{ success: boolean; matrix: number[][] }>),

  switchCameraSource: (data: { source_type: 'webcam' | 'ip_camera' | 'mobile_browser'; url?: string; device_index?: number }) =>
    fetch(`${API_BASE}/api/video/switch-source`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(handleResponse<{ success: boolean; source_name?: string; source_type?: string; error?: string }>),

  // ---------- Multi-Camera ----------

  addCamera: (data: { camera_id: string; source_type: string; display_name?: string; url?: string; device_index?: number }) =>
    fetch(`${API_BASE}/api/video/cameras`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(handleResponse<{ success: boolean; camera_id?: string; display_name?: string; error?: string }>),

  removeCamera: (cameraId: string) =>
    fetch(`${API_BASE}/api/video/cameras/${encodeURIComponent(cameraId)}`, {
      method: 'DELETE',
    }).then(handleResponse<{ success: boolean; camera_id: string }>),

  listCameras: () =>
    fetch(`${API_BASE}/api/video/cameras`).then(handleResponse<{ cameras: CameraInfo[]; total: number }>),

  getGlobalTracks: () =>
    fetch(`${API_BASE}/api/video/global-tracks`).then(handleResponse<{ tracks: GlobalTrack[]; total: number }>),
};

