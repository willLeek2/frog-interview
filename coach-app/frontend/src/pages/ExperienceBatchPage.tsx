import { useCallback, useEffect, useState } from 'react'
import { useParams, useOutletContext } from 'react-router-dom'

import {
  getExperienceBatchDetail,
  deleteExperienceQuestion,
  listExperienceBatchTasks,
} from '../lib/api'
import type { ExperienceBatchDetail, ExperienceProcessTask } from '../lib/types'

interface OutletContext {
  onProcessBatch: (batchId: string) => Promise<void>
}

function isTaskActive(status: string): boolean {
  return status === 'queued' || status === 'running'
}

function latestTask(tasks: ExperienceProcessTask[]): ExperienceProcessTask | null {
  return tasks[0] ?? null
}

function statusClass(status: string): string {
  if (status === 'completed') return 'bg-emerald-100 text-emerald-700'
  if (status === 'failed') return 'bg-rose-100 text-rose-700'
  if (status === 'running') return 'bg-amber-100 text-amber-700'
  if (status === 'queued') return 'bg-indigo-100 text-indigo-700'
  return 'bg-primary-100 text-primary-700'
}

function statusLabel(status: string): string {
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'running') return '处理中'
  if (status === 'queued') return '排队中'
  return '待处理'
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

export default function ExperienceBatchPage() {
  const { batchId } = useParams<{ batchId: string }>()
  const { onProcessBatch } = useOutletContext<OutletContext>()
  const [detail, setDetail] = useState<ExperienceBatchDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [tasks, setTasks] = useState<ExperienceProcessTask[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [processing, setProcessing] = useState(false)

  const loadDetail = useCallback(async (id: string) => {
    setLoading(true)
    try {
      const data = await getExperienceBatchDetail(id)
      setDetail(data)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTasks = useCallback(async (id: string) => {
    setTasksLoading(true)
    try {
      const rows = await listExperienceBatchTasks(id, 30)
      setTasks(rows)
    } finally {
      setTasksLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!batchId) return
    void loadDetail(batchId)
    void loadTasks(batchId)
  }, [batchId, loadDetail, loadTasks])

  useEffect(() => {
    if (!batchId) return
    const currentTask = latestTask(tasks)
    if (!currentTask || !isTaskActive(currentTask.status)) return

    const timer = window.setInterval(() => {
      void loadTasks(batchId)
      void loadDetail(batchId)
    }, 2500)

    return () => window.clearInterval(timer)
  }, [batchId, loadDetail, loadTasks, tasks])

  const handleDeleteQuestion = async (questionId: string) => {
    if (!batchId) return
    if (!confirm('确定要删除这道题目吗？')) return
    setDeletingId(questionId)
    setError(null)
    try {
      await deleteExperienceQuestion(batchId, questionId)
      // Refresh detail after delete
      await loadDetail(batchId)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setDeletingId(null)
    }
  }

  const handleProcess = async () => {
    if (!batchId) return
    const currentTask = latestTask(tasks)
    if ((currentTask && isTaskActive(currentTask.status)) || processing) return
    setError(null)
    setProcessing(true)
    try {
      await onProcessBatch(batchId)
      await loadTasks(batchId)
      await loadDetail(batchId)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setProcessing(false)
    }
  }

  const currentTask = latestTask(tasks)
  const activeTask = currentTask && isTaskActive(currentTask.status) ? currentTask : null

  if (!batchId) {
    return (
      <div className="flex h-full items-center justify-center text-primary-600">
        无效的批次 ID
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header with actions */}
      <section className="rounded-2xl border border-primary-100 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-primary-900">批次详情</h3>
          <button
            type="button"
            onClick={handleProcess}
            disabled={loading || processing || !!activeTask}
            className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
          >
            {activeTask ? '处理中...' : processing ? '提交中...' : '处理当前批次'}
          </button>
        </div>

        {loading && <p className="text-sm text-primary-600">加载中...</p>}
        {error && <p className="mb-3 text-xs text-rose-600">{error}</p>}

        {detail?.batch && (
          <div className="mb-3 grid grid-cols-2 gap-2 rounded-xl bg-primary-50 p-3 text-xs text-primary-700 md:grid-cols-4">
            <p>状态：{statusLabel(detail.batch.status)}</p>
            <p>图片：{detail.batch.image_count}</p>
            <p>题目：{detail.batch.question_count}</p>
            <p>创建：{formatDateTime(detail.batch.created_at)}</p>
          </div>
        )}

        {activeTask && (
          <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
            当前任务正在处理中，页面会自动刷新任务状态和题目列表。
          </div>
        )}

        {tasks.length > 0 && (
          <div className="rounded-xl border border-primary-100 p-3">
            <p className="mb-2 text-xs font-semibold text-primary-800">任务历史</p>
            <div className="space-y-2">
              {tasks.slice(0, 8).map((task) => (
                <div key={task.id} className="flex items-center justify-between text-xs">
                  <span className="text-primary-700">{task.id.slice(0, 12)}</span>
                  <span className={`rounded-full px-2 py-0.5 ${statusClass(task.status)}`}>
                    {statusLabel(task.status)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        {tasksLoading && <p className="mt-2 text-xs text-primary-600">任务加载中...</p>}
      </section>

      {/* Questions list */}
      <section className="rounded-2xl border border-primary-100 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-primary-900">
          题目列表 ({detail?.questions?.length || 0})
        </h3>

        {detail?.questions && detail.questions.length > 0 ? (
          <div className="space-y-2">
            {detail.questions.map((question) => (
              <div
                key={question.id}
                className="group relative rounded-xl border border-primary-100 p-3 transition hover:border-primary-200"
              >
                <button
                  type="button"
                  onClick={() => handleDeleteQuestion(question.id)}
                  disabled={deletingId === question.id}
                  className="absolute right-2 top-2 rounded p-1 text-primary-400 opacity-0 transition hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100 disabled:opacity-50"
                  title="删除题目"
                >
                  {deletingId === question.id ? '...' : '×'}
                </button>
                <p className="pr-6 text-sm text-primary-900">{question.question_text}</p>
                <p className="mt-2 text-xs text-primary-600">
                  tags: {question.topic_tags.join(' / ') || '-'} · 置信度{' '}
                  {question.confidence.toFixed(2)}
                  {question.extra?.is_algorithm === true && (
                    <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-amber-700">
                      算法题
                    </span>
                  )}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-primary-600">
            {loading ? '加载中...' : '当前批次尚未抽取出题目。'}
          </p>
        )}
      </section>
    </div>
  )
}
