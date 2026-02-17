import type {
  ExperienceBatch,
  ExperienceBatchDetail,
  ExperienceClusterDetail,
  ExperienceHotQuestion,
  ExperienceProcessTask,
  FeatureType,
  Message,
  Session,
  SessionDetail,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export async function listSessions(feature: FeatureType): Promise<Session[]> {
  return request<Session[]>(`/api/v1/chat/sessions?feature=${feature}`)
}

export async function createSession(feature: FeatureType): Promise<Session> {
  return request<Session>('/api/v1/chat/sessions', {
    method: 'POST',
    body: JSON.stringify({ feature }),
  })
}

export async function getSessionDetail(sessionId: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/api/v1/chat/sessions/${sessionId}`)
}

export async function sendMessage(sessionId: string, content: string): Promise<Message> {
  return request<Message>(`/api/v1/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export async function rebuildIndex(): Promise<{ files_scanned: number; chunks_indexed: number }> {
  return request('/api/v1/index/rebuild', { method: 'POST' })
}

export async function transcribeAudio(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch(`${API_BASE}/api/v1/audio/transcribe`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Transcribe failed: ${res.status}`)
  }
  const data = (await res.json()) as { text: string }
  return data.text || ''
}

export async function listExperienceBatches(): Promise<ExperienceBatch[]> {
  return request<ExperienceBatch[]>('/api/v1/experience/batches')
}

export async function getExperienceBatchDetail(batchId: string): Promise<ExperienceBatchDetail> {
  return request<ExperienceBatchDetail>(`/api/v1/experience/batches/${batchId}`)
}

export async function processExperienceBatch(batchId: string): Promise<{
  task_id: string
  batch_id: string
  status: string
  already_exists: boolean
}> {
  return request(`/api/v1/experience/batches/${batchId}/process`, { method: 'POST' })
}

export async function getExperienceTask(taskId: string): Promise<ExperienceProcessTask> {
  return request<ExperienceProcessTask>(`/api/v1/experience/tasks/${taskId}`)
}

export async function listExperienceBatchTasks(batchId: string, limit = 30): Promise<ExperienceProcessTask[]> {
  return request<ExperienceProcessTask[]>(`/api/v1/experience/batches/${batchId}/tasks?limit=${limit}`)
}

export async function createExperienceBatch(payload: {
  files: File[]
  company?: string
  businessLine?: string
  notes?: string
  interviewAt?: string
}): Promise<ExperienceBatch> {
  const form = new FormData()
  payload.files.forEach((file) => form.append('files', file))
  if (payload.company) form.append('company', payload.company)
  if (payload.businessLine) form.append('business_line', payload.businessLine)
  if (payload.notes) form.append('notes', payload.notes)
  if (payload.interviewAt) form.append('interview_at', payload.interviewAt)

  const res = await fetch(`${API_BASE}/api/v1/experience/batches`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Upload failed: ${res.status}`)
  }
  return (await res.json()) as ExperienceBatch
}

export async function listExperienceHotQuestions(params?: {
  days?: number
  company?: string
  limit?: number
}): Promise<ExperienceHotQuestion[]> {
  const query = new URLSearchParams()
  if (params?.days) query.set('days', String(params.days))
  if (params?.company) query.set('company', params.company)
  if (params?.limit) query.set('limit', String(params.limit))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return request<ExperienceHotQuestion[]>(`/api/v1/experience/hot-questions${suffix}`)
}

export async function getExperienceClusterDetail(
  clusterId: string,
  limit = 200,
): Promise<ExperienceClusterDetail> {
  return request<ExperienceClusterDetail>(`/api/v1/experience/clusters/${clusterId}?limit=${limit}`)
}
