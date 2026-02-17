export type FeatureType = 'random' | 'explain' | 'quiz' | 'experience'

export type RoleType = 'user' | 'assistant' | 'system'

export interface Citation {
  title?: string
  url?: string
  snippet?: string
  source?: string
}

export interface Session {
  id: string
  feature: FeatureType
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  session_id: string
  role: RoleType
  content: string
  citations: Citation[]
  metadata: Record<string, unknown>
  created_at: string
}

export interface SessionDetail {
  session: Session
  messages: Message[]
}

export type ExperienceBatchStatus = 'pending' | 'running' | 'completed' | 'failed'
export type ExperienceTaskStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface ExperienceBatch {
  id: string
  company?: string | null
  business_line?: string | null
  interview_at?: string | null
  status: ExperienceBatchStatus
  error_message?: string | null
  image_count: number
  question_count: number
  created_at: string
  updated_at: string
}

export interface ExperienceImage {
  id: string
  original_name: string
  content_type?: string | null
  file_size: number
  order_index: number
  created_at: string
}

export interface ExperienceQuestion {
  id: string
  cluster_id: string
  question_text: string
  normalized_question: string
  topic_tags: string[]
  company?: string | null
  business_line?: string | null
  interview_round?: string | null
  confidence: number
  extra: Record<string, unknown>
  created_at: string
}

export interface ExperienceBatchDetail {
  batch: ExperienceBatch
  images: ExperienceImage[]
  questions: ExperienceQuestion[]
}

export interface ExperienceHotQuestion {
  cluster_id: string
  canonical_question: string
  topic_tags: string[]
  companies: string[]
  total_count: number
  last_seen_at: string
}

export interface ExperienceProcessTask {
  id: string
  batch_id: string
  status: ExperienceTaskStatus
  result: Record<string, unknown>
  error_message?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
}

export interface ExperienceClusterVariant {
  normalized_question: string
  sample_question: string
  count: number
  last_seen_at: string
  companies: string[]
}

export interface ExperienceClusterSourceBatch {
  batch_id: string
  company?: string | null
  business_line?: string | null
  interview_at?: string | null
  question_count: number
  last_seen_at: string
}

export interface ExperienceClusterDetail {
  cluster_id: string
  canonical_question: string
  topic_tags: string[]
  companies: string[]
  total_count: number
  first_seen_at: string
  last_seen_at: string
  variants: ExperienceClusterVariant[]
  source_batches: ExperienceClusterSourceBatch[]
}
