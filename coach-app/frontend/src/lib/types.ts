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

export type ChatRunTaskStatus = 'queued' | 'running' | 'completed' | 'failed'
export type ChatRunStage =
  | 'queued'
  | 'local_retrieval'
  | 'web_research'
  | 'tool_call'
  | 'llm_generation'
  | 'saving'
  | 'completed'
  | 'failed'

export interface ChatRunTaskCreateResponse {
  task_id: string
  session_id: string
  status: ChatRunTaskStatus
  stage: ChatRunStage
  stage_label: string
}

export interface ChatRunEvent {
  stage: ChatRunStage
  label: string
  detail?: string
  at: string
}

export interface ChatRunTask {
  id: string
  session_id: string
  user_message_id?: string | null
  result_message_id?: string | null
  status: ChatRunTaskStatus
  stage: ChatRunStage
  stage_label: string
  events: ChatRunEvent[]
  metadata: Record<string, unknown>
  error_message?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
}

export interface CitationContent {
  title?: string | null
  url?: string | null
  source?: string | null
  render_mode: 'markdown' | 'raw_text' | 'external'
  content: string
  external_url?: string | null
  truncated: boolean
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

export interface AlgorithmQuestion {
  id: string
  question_text: string
  normalized_question: string
  topic_tags: string[]
  company?: string | null
  business_line?: string | null
  interview_round?: string | null
  confidence: number
  batch_id: string
  cluster_id: string
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

// Index rebuild types
export type IndexRebuildMode = 'full' | 'incremental'
export type IndexRebuildTaskStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface IndexRebuildTask {
  id: string
  status: IndexRebuildTaskStatus
  mode: IndexRebuildMode
  files_total: number
  files_scanned: number
  files_added: number
  files_updated: number
  files_unchanged: number
  chunks_indexed: number
  topics_count: number
  error_message?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
}
