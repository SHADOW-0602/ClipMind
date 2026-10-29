export type Platform = "instagram" | "youtube" | "tiktok" | "linkedin" | "x";

export interface BrandProfile {
  id: string;
  name: string;
  tone_description: string;
  voice_dos: string[];
  voice_donts: string[];
  banned_words: string[];
  example_posts: string[];
  target_audience: string;
  created_at: string;
  updated_at: string;
}

export interface BrandProfileInput {
  name: string;
  tone_description?: string;
  voice_dos?: string[];
  voice_donts?: string[];
  banned_words?: string[];
  example_posts?: string[];
  target_audience?: string;
}

export interface MediaAsset {
  id: string;
  project_id: string;
  kind: "video" | "audio" | "text" | string;
  original_filename: string;
  path: string;
  normalized_path: string | null;
  audio_path: string | null;
  duration_s: number;
  width: number;
  height: number;
  fps: number;
  size_bytes: number;
  status: string;
  created_at: string;
  media_url: string | null;
  audio_url: string | null;
  frames: Array<{ timestamp?: number; url?: string; path?: string }>;
}

export interface JobStage {
  name: string;
  label: string;
  status: "pending" | "running" | "complete" | "failed" | string;
  progress: number;
  message: string;
}

export interface JobEvent {
  seq: number;
  type: string;
  stage: string;
  message: string;
  progress: number;
  ts: number;
}

export interface Job {
  id: string;
  project_id: string;
  stage: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | string;
  progress: number;
  error: string | null;
  stages_json: JobStage[];
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface CopyVariant {
  id: string;
  clip_id: string;
  platform: Platform | string;
  caption: string;
  hooks: string[];
  hashtags: string[];
  cta: string;
  version: number;
}

export interface Clip {
  id: string;
  project_id: string;
  asset_id: string;
  start: number;
  end: number;
  title: string;
  hook: string;
  source_quote: string;
  score: number;
  rationale: string;
  status: "selected" | "rendered" | "failed" | "rejected" | string;
  render_path: string | null;
  srt_path: string | null;
  thumbnail_path: string | null;
  risk_flags_json: string[];
  copy_variants: CopyVariant[];
  media_url: string | null;
  thumbnail_url: string | null;
  srt_url: string | null;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  brand_profile_id: string | null;
  status: string;
  error: string | null;
  brand_profile: BrandProfile | null;
  assets: MediaAsset[];
  clips: Clip[];
  latest_job: Job | null;
}

export interface ProjectListItem {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  status: string;
  brand_profile_id: string | null;
  duration_s: number;
  clip_count: number;
  thumbnail_url: string | null;
}

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
  words?: TranscriptWord[];
}

export interface Transcript {
  id: string;
  asset_id: string;
  language: string;
  text: string;
  segments_json: TranscriptSegment[];
  provider: string;
}

export interface Summary {
  tldr: string;
  bullets: string[];
  chapters: Array<{ start: number; title: string; summary?: string }>;
  quotes: Array<{ start: number; text: string }>;
}

export interface InsightScores {
  hook_strength: number;
  pacing: number;
  clarity: number;
  emotional_peaks: number;
}

export interface InsightClip {
  clip_id: string;
  clip_index: number;
  title: string;
  scores: InsightScores;
  predicted_performance: "low" | "medium" | "high";
  reasoning: string;
  improvements: string[];
  risk_flags?: string[];
  safety_notes?: string[];
}

export interface InsightsReport {
  generated_at: string;
  headline: string;
  summary: string;
  overall: InsightScores;
  predicted_performance: "low" | "medium" | "high";
  confidence: "low" | "medium" | "high";
  improvements: string[];
  clips: InsightClip[];
  metrics: {
    duration_s?: number;
    word_count?: number;
    wpm: number;
    pause_ratio: number;
    filler_rate: number;
    clip_metrics?: Array<Record<string, unknown>>;
  };
  methodology: string;
  source: { kind: string; duration_s: number; filename: string };
}

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  cost_usd: number;
  asr_cost_usd: number;
  total_cost_usd: number;
  budget_usd: number;
  remaining_usd: number;
  credits_remaining_usd: number;
  calls: number;
}

export interface UsageCall {
  id: string;
  kind: "model" | "asr";
  job_id: string | null;
  provider: string;
  model: string;
  purpose: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  audio_seconds: number;
  cost_usd: number;
  latency_ms: number;
  cache_hit: boolean;
  created_at: string;
}

export interface Health {
  status: string;
  app: string;
  version: string;
  provider: string;
  model: string;
  asr_provider: string;
  asr_model: string;
  max_budget_usd: number;
}

export interface SystemInfo {
  version: string;
  environment: string;
  provider: string;
  provider_base_url: string;
  model: string;
  asr_provider: string;
  asr_model: string;
  force_whisper: boolean;
  max_budget_usd: number;
  hackathon_credits_usd: number;
  input_price_per_m: number;
  cached_input_price_per_m: number;
  output_price_per_m: number;
  asr_usd_per_hour: number;
  max_upload_mb: number;
  max_duration_s: number;
  min_clip_s: number;
  max_clip_s: number;
  job_concurrency: number;
  auto_resume_jobs: boolean;
  public_api_url: string;
  data_dir: string;
  cors_origins: string[];
}

export interface ProcessOptions {
  n_clips: number;
  platforms: Platform[];
  min_clip_s: number;
  max_clip_s: number;
  brand_profile_id?: string | null;
  regenerate?: boolean;
}

export type UploadResult = MediaAsset;
