export type UserRole = 'manager' | 'staff' | 'owner' | 'queue' | 'inventory' | 'calibration' | 'camera';

export interface HeatmapCell {
  row: number;
  col: number;
  count: number;
}

export interface HeatmapResponse {
  cells: HeatmapCell[];
  grid_rows: number;
  grid_cols: number;
  cell_size_m: number;
  floor_width_m: number;
  floor_height_m: number;
  start_ts: number;
  end_ts: number;
}

export interface DwellEvent {
  id: number;
  timestamp: number;
  zone_id: string;
  qualifying_time_s: number;
  confidence: string;
}

export interface DwellResponse {
  events: DwellEvent[];
  start_ts: number;
  end_ts: number;
}

export interface FootfallResponse {
  count_in: number;
  count_out: number;
  total: number;
  start_ts: number;
  end_ts: number;
}

export interface ManagerSummary {
  footfall: { in: number; out: number };
  footfall_rate_per_min: number;
  dwell_by_zone: Record<string, { count: number; total_time_s: number }>;
  dwell_event_count: number;
  timestamp: number;
}

export interface LiveDetection {
  track_id: number;
  global_id?: number | null;
  camera_id?: string;
  centroid_px: [number, number];
  centroid_world: [number, number] | null;
  confidence: number;
  gender?: string;
  gender_confidence?: number;
  dwell_time_s?: number;
}

export interface DetectionStreamData {
  persons: LiveDetection[];
  count: number;
  is_high_density: boolean;
  camera_id?: string;
}

export interface GlobalTrack {
  global_id: number;
  camera_id: string;
  local_track_id: number;
  gender: string;
  gender_confidence: number;
  dwell_time_s: number;
  first_seen_time: number;
  last_seen_time: number;
  cameras_visited: string[];
  total_cameras: number;
}

export interface CameraInfo {
  camera_id: string;
  display_name: string;
  source_type: string;
  running: boolean;
  tracks_count: number;
  fps: number;
  has_frame: boolean;
}

export interface AlertItem {
  id: string;
  type: 'queue' | 'stockout' | 'density' | 'info';
  title: string;
  message: string;
  timestamp: number;
  details?: Record<string, any>;
  dismissed?: boolean;
}

export interface QueuePrediction {
  service_rate_per_counter: number;
  total_capacity: number;
  predicted_checkout_demand: number;
  congestion_gap: number;
  predicted_queue_size: number;
  max_acceptable_queue: number;
  should_open_counter: boolean;
  smoothed_footfall_rate: number;
  smoothed_service_time: number;
  queue_sizes: Record<string, number>;
  counters_open: number;
  current_total_queue: number;
  footfall_rate: number;
}

export interface QueueConfig {
  avg_service_time_s: number;
  conversion_rate: number;
  max_acceptable_wait_time_s: number;
  avg_shopping_time_s: number;
  smoothing_alpha: number;
}

export interface InventorySlot {
  id: number;
  slot_name: string;
  total_stock: number;
  sold: number;
  consecutive_empty: number;
  is_stocked_out: number;
  reference_image_hash?: string;
  created_at: number;
  available_stock?: number;
}

export interface ROIResponse {
  baseline_monthly_revenue: number;
  current_monthly_revenue: number;
  revenue_uplift: number;
  stockouts_prevented_value: number;
  total_monthly_benefit: number;
  monthly_system_cost: number;
  monthly_roi_percent: number;
  payback_month: number;
  live_footfall: number;
  conversion_rate: number;
  avg_basket_value: number;
}

export interface CalibrationStatus {
  calibrated: boolean;
  matrix?: number[][];
  num_points?: number;
  floor_width_m?: number;
  floor_height_m?: number;
}
