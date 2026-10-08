export interface AppItem {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  icon_url?: string | null;
  status: string;
  batch_count?: number;
}

export interface VideoInfo {
  id: string;
  youtube_video_id: string;
  duration?: number | null;
  resolution?: string | null;
  file_size?: number | null;
  title?: string | null;
}

export interface PDFInfo {
  id: string;
  b2_object_key: string;
  b2_bucket?: string | null;
  file_name?: string | null;
  file_size?: number | null;
  page_count?: number | null;
}

export interface LectureItem {
  id: string;
  lecture_index: number;
  title: string;
  provider?: string | null;
  source_url?: string | null;
  has_video: boolean;
  has_pdf: boolean;
  publication_status: "PUBLISHED" | "UNPUBLISHED" | "DRAFT";
  video?: VideoInfo | null;
  pdf?: PDFInfo | null;
  folder_id?: string | null;
  subject_id?: string | null;
  batch_id?: string | null;
}

export interface FolderItem {
  id: string;
  name: string;
  unit_number?: string | null;
  sort_order: number;
  lectures: LectureItem[];
}

export interface SubjectItem {
  id: string;
  name: string;
  code?: string | null;
  sort_order: number;
  folders: FolderItem[];
}

export interface BatchItem {
  id: string;
  name: string;
  slug: string;
  category?: string | null;
  branch?: string | null;
  semester?: string | null;
  academic_year?: string | null;
  thumbnail_url?: string | null;
  status: string;
  app_id?: string | null;
  app_name?: string | null;
  app?: AppItem | null;
  subjects?: SubjectItem[];
  subject_count?: number;
}

export interface StudentUser {
  id: string;
  name: string;
  email: string;
  status?: string;
  created_at?: string | null;
  last_login_at?: string | null;
  enrolled_batches_count?: number;
  enrolled_batch_ids?: string[];
}

export interface StudentActivityItem {
  lecture_id: string;
  lecture_title: string;
  lecture_index: number;
  batch_name: string;
  batch_slug: string;
  playback_seconds: number;
  completed: boolean;
  last_accessed_at?: string | null;
}

export interface AIAction {
  label: string;
  href: string;
}

export interface AIResponse {
  reply: string;
  actions?: AIAction[];
}

export interface JobItem {
  id: string;
  bot_id: string;
  batch_id?: string | null;
  lecture_id?: string | null;
  provider?: string | null;
  status: string;
  progress_percent: number;
  current_step?: string | null;
  error_message?: string | null;
  created_at?: string | null;
}

export interface BlockedCheckpoint {
  batch_id: string;
  batch_name: string;
  lecture_index: number;
  lecture_title: string;
  stage: string;
  reason: string;
  size_mb: number;
  duration_sec: number;
  created_at?: string | null;
}

export interface YouTubeDiagnostics {
  channel: {
    auth_status: string;
    connected: boolean;
    api_project_client_id: string;
    channel_id?: string | null;
    channel_title?: string | null;
    custom_url?: string | null;
    description?: string | null;
    long_uploads_status: string;
    is_linked: boolean;
    privacy_status: string;
    view_count: number;
    video_count: number;
    subscriber_count: number;
    error?: string | null;
    cached: boolean;
    last_refreshed_at?: string | null;
  };
  platform_upload_history: {
    label: string;
    total_recorded_uploads: number;
    uploads_last_24h: number;
    uploads_last_7d: number;
    uploads_last_30d: number;
    last_successful_upload_at?: string | null;
    failed_upload_attempts: number;
    last_youtube_error?: string | null;
    last_upload_limit_exceeded_at?: string | null;
  };
  queues: {
    publishing_queue_count: number;
    blocked_checkpoints_count: number;
    blocked_checkpoints: BlockedCheckpoint[];
  };
  limits_policy: {
    label: string;
    error_classification: {
      uploadLimitExceeded: string;
      quotaExceeded: string;
    };
    disclaimer: string;
  };
}
