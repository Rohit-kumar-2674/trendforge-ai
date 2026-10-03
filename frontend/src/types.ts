export type Point = { date: string; value: number };
export type Probabilities = { up: number; sideways: number; down: number };
export interface Analogue { start_date: string; end_date: string; outcome_date: string; similarity: number; future_return: number; outcome: string }
export interface Forecast {
  id: string; entity_id: string; issued_at: string; as_of: string; generated_at: string;
  horizon: number; horizon_unit: string; target_metric: string; probabilities: Probabilities;
  direction: string; confidence: string; confidence_reasons: string[]; model_version: string;
  analogue_count: number; analogue_similarity: number; analogues: Analogue[];
  class_definition: string; calibration: string; status: string; out_of_distribution: boolean;
  snapshot_hash: string; features_hash: string; synthetic: boolean;
  outcome: { actual_class: string; actual_return: number; observed_at: string; correct: boolean } | null;
}
export interface Score {
  current_score?: number; components?: Record<string, number | null>;
  growth_7_periods?: number; growth_30_periods?: number; relative_acceleration?: number;
  velocity?: number; acceleration?: number; jerk?: number; volatility?: number;
  early_signal_score?: number; breakout_score?: number; lifecycle_stage?: string;
  observation?: string; analysis?: string; inference?: string;
  source_count?: number; primary_provider?: string; sample_size?: number;
  observed_value?: number; saturation?: string; anomaly_detected?: boolean; anomaly_z?: number;
  supporting_signals?: string[]; contradicting_signals?: string[];
  quality?: { score: number; sample_size: number; flags: string[]; completeness: number };
  technicals?: Record<string, number | string | null>;
  effective_weights?: Record<string, number>; weight_coverage?: number;
}
export interface Trend {
  id: string; name: string; domain: string; category: string; region: string; unit: string;
  cadence: string; primary_metric: string; synthetic: boolean; analytics_allowed: boolean;
  last_updated: string | null; score: Score; forecast: Forecast | null; forecast_status: string;
  sparkline: Point[]; watchlisted: boolean;
  freshness: { status: string; source_timestamp: string | null; retrieved_at: string | null; age_hours: number | null; expected_interval_hours: number };
  timeline?: { occurred_at: string; kind: string; message: string }[];
}
export interface Provider { name: string; status: string; capability: string; message: string; last_success: string | null; records: number; expected_interval_hours: number; stats: { requests?: number; successes?: number; latency_ms?: number; quota_remaining?: string | null } }
export interface Event { id: string; entity_id: string; name: string; occurred_at: string; kind: string; message: string }
export interface Evidence { id: number; metric: string; value: number; provider: string; source_timestamp: string; retrieved_at: string; source_url: string | null; unit: string; synthetic: boolean }
export interface History { observations: (Point & { provider: string; unit: string })[]; scores: { date: string; score: number; momentum: number; acceleration: number }[]; metric: string; unit: string }
export interface Metric { sample_size: number; accuracy?: number; brier_score?: number; log_loss?: number; balanced_accuracy?: number; f1_macro?: number; reliability?: Record<string, { predicted_probability: number; actual_frequency: number; sample_size: number }[]> }
export interface TrackRecord { issued: number; resolved: number; pending: number; synthetic: boolean; metrics: Metric; note: string }
export interface Backtest { entity: string; synthetic: boolean; production_changed: boolean; metrics: Metric; horizon: number; validation: string; limitations: string[] }
export interface Relationship { status: string; left: string; right: string; best_lag_days?: number; correlation?: number; sample_size?: number; caution: string; samples: { lag_days: number; correlation: number }[] }
