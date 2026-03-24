import { useCallback, useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'

import {
  createExperienceBatch,
  listExperienceBatches,
  processExperienceBatch,
  listExperienceBatchTasks,
  getExperienceTask,
} from '../lib/api'
import type {
  ExperienceBatch,
  ExperienceProcessTask,
} from '../lib/types'

type MobileTab = 'upload' | 'batches'

const MOBILE_TABS: Array<{ key: MobileTab; label: string }> = [
  { key: 'upload', label: '上传' },
  { key: 'batches', label: '批次' },
]

interface PendingUploadFile {
  id: string
  file: File
  previewUrl: string
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

function isTaskActive(status: string): boolean {
  return status === 'queued' || status === 'running'
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

export default function ExperienceLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileTab, setMobileTab] = useState<MobileTab>('upload')
  const [files, setFiles] = useState<File[]>([])
  const [company, setCompany] = useState('')
  const [businessLine, setBusinessLine] = useState('')
  const [interviewAt, setInterviewAt] = useState('')
  const [notes, setNotes] = useState('')

  const [batches, setBatches] = useState<ExperienceBatch[]>([])
  const [batchesLoading, setBatchesLoading] = useState(false)
  const [tasksByBatch, setTasksByBatch] = useState<Record<string, ExperienceProcessTask[]>>({})
  const [pollingTaskMap, setPollingTaskMap] = useState<Record<string, string>>({})

  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [previewingFileId, setPreviewingFileId] = useState<string | null>(null)

  const pendingFiles = useMemo<PendingUploadFile[]>(
    () =>
      files.map((file) => ({
        id: `${file.name}-${file.size}-${file.lastModified}`,
        file,
        previewUrl: URL.createObjectURL(file),
      })),
    [files],
  )

  const previewingFile = useMemo(
    () => pendingFiles.find((item) => item.id === previewingFileId) ?? null,
    [pendingFiles, previewingFileId],
  )

  useEffect(() => {
    return () => {
      pendingFiles.forEach((item) => URL.revokeObjectURL(item.previewUrl))
    }
  }, [pendingFiles])

  const appendFiles = useCallback((nextFiles: File[]) => {
    if (nextFiles.length === 0) return
    setFiles((prev) => {
      const merged = [...prev]
      const seen = new Set(prev.map((file) => `${file.name}-${file.size}-${file.lastModified}`))
      nextFiles.forEach((file) => {
        const key = `${file.name}-${file.size}-${file.lastModified}`
        if (seen.has(key)) return
        merged.push(file)
        seen.add(key)
      })
      return merged.slice(0, 20)
    })
  }, [])

  const removeFile = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.filter((file) => `${file.name}-${file.size}-${file.lastModified}` !== fileId),
    )
    setPreviewingFileId((prev) => (prev === fileId ? null : prev))
  }, [])

  const loadBatches = useCallback(async () => {
    setBatchesLoading(true)
    try {
      const rows = await listExperienceBatches()
      setBatches(rows)
    } finally {
      setBatchesLoading(false)
    }
  }, [])

  const loadBatchTasks = useCallback(async (batchId: string) => {
    const rows = await listExperienceBatchTasks(batchId, 30)
    setTasksByBatch((prev) => ({ ...prev, [batchId]: rows }))
    setPollingTaskMap((prev) => {
      const next: Record<string, string> = {}
      Object.entries(prev).forEach(([taskId, ownerBatchId]) => {
        if (ownerBatchId !== batchId) next[taskId] = ownerBatchId
      })
      rows.forEach((task) => {
        if (isTaskActive(task.status)) next[task.id] = batchId
      })
      return next
    })
  }, [])

  useEffect(() => {
    void loadBatches()
  }, [loadBatches])

  // Poll active tasks
  useEffect(() => {
    const taskIds = Object.keys(pollingTaskMap)
    if (taskIds.length === 0) return

    const timer = window.setInterval(() => {
      void (async () => {
        const rows = await Promise.all(
          taskIds.map(async (taskId) => {
            try {
              return await getExperienceTask(taskId)
            } catch {
              return null
            }
          }),
        )
        const tasks = rows.filter(Boolean) as ExperienceProcessTask[]
        if (tasks.length === 0) return

        const finishedBatchIds = new Set<string>()

        setTasksByBatch((prev) => {
          const next = { ...prev }
          tasks.forEach((task) => {
            const items = [...(next[task.batch_id] || [])]
            const idx = items.findIndex((x) => x.id === task.id)
            if (idx >= 0) items[idx] = task
            else items.unshift(task)
            items.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
            next[task.batch_id] = items.slice(0, 30)
            if (!isTaskActive(task.status)) finishedBatchIds.add(task.batch_id)
          })
          return next
        })

        setPollingTaskMap((prev) => {
          const next: Record<string, string> = {}
          Object.entries(prev).forEach(([taskId, batchId]) => {
            const task = tasks.find((item) => item.id === taskId)
            if (!task || !isTaskActive(task.status)) return
            next[taskId] = batchId
          })
          return next
        })

        if (finishedBatchIds.size > 0) {
          void loadBatches()
        }
      })()
    }, 2500)

    return () => window.clearInterval(timer)
  }, [loadBatches, pollingTaskMap])

  // Load tasks for visible batches
  useEffect(() => {
    batches.forEach((batch) => {
      void loadBatchTasks(batch.id)
    })
  }, [batches, loadBatchTasks])

  const onUpload = async () => {
    if (files.length === 0 || uploading) return
    setUploading(true)
    setError(null)
    try {
      const row = await createExperienceBatch({
        files,
        company: company.trim() || undefined,
        businessLine: businessLine.trim() || undefined,
        notes: notes.trim() || undefined,
        interviewAt: interviewAt || undefined,
      })
      setFiles([])
      setCompany('')
      setBusinessLine('')
      setInterviewAt('')
      setNotes('')
      setPreviewingFileId(null)
      await loadBatches()
      navigate(`/experience/batches/${row.id}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  const onProcessBatch = async (batchId: string) => {
    setError(null)
    try {
      const task = await processExperienceBatch(batchId)
      setPollingTaskMap((prev) => ({ ...prev, [task.task_id]: batchId }))
      await loadBatchTasks(batchId)
      await loadBatches()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    const droppedFiles = Array.from(e.dataTransfer.files).filter((file) =>
      file.type.startsWith('image/'),
    )
    appendFiles(droppedFiles)
  }, [appendFiles])

  const isBatchActive = useMemo(() => {
    return location.pathname.includes('/experience/batches/')
  }, [location.pathname])

  const isHotQuestionsActive = useMemo(() => {
    return location.pathname.includes('/experience/hot-questions')
  }, [location.pathname])

  const uploadPanel = (
    <section className="rounded-2xl border border-primary-100 bg-white p-3 md:p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-primary-900">上传面经截图</h3>
        <span className="text-xs text-primary-500">单次最多 20 张</span>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`mb-3 flex w-full flex-col items-center rounded-xl border border-dashed px-4 py-5 text-center transition-colors ${
          isDragging
            ? 'border-primary-500 bg-primary-100'
            : 'border-primary-300 bg-primary-50/70'
        }`}
      >
        <label className="flex w-full cursor-pointer flex-col items-center">
          <span className="text-sm font-medium text-primary-700">点击或拖拽上传截图</span>
          <span className="mt-1 text-xs text-primary-500">支持 PNG / JPG / WEBP</span>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            className="hidden"
            onChange={(e) => {
              appendFiles(Array.from(e.target.files || []))
              e.currentTarget.value = ''
            }}
          />
        </label>
      </div>

      {pendingFiles.length > 0 && (
        <div className="mb-3 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-primary-700">待上传图片</p>
            <p className="text-[11px] text-primary-500">点击卡片预览，右上角可删除</p>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {pendingFiles.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setPreviewingFileId(item.id)}
                className="group relative flex items-center gap-3 rounded-2xl border border-primary-200 bg-primary-50/70 p-2 text-left transition hover:border-primary-400 hover:bg-white"
              >
                <img
                  src={item.previewUrl}
                  alt={item.file.name}
                  className="h-12 w-12 shrink-0 rounded-xl border border-primary-100 object-cover"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-primary-900">{item.file.name}</p>
                  <p className="text-xs text-primary-600">{Math.max(1, Math.round(item.file.size / 1024))} KB</p>
                </div>
                <span
                  onClick={(e) => {
                    e.stopPropagation()
                    removeFile(item.id)
                  }}
                  className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-white/90 text-xs text-primary-500 shadow-sm transition hover:bg-rose-50 hover:text-rose-600"
                >
                  ×
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="公司（例如：字节）"
          className="w-full rounded-xl border border-primary-200 px-3 py-2 text-sm outline-none focus:border-primary-400"
        />
        <input
          value={businessLine}
          onChange={(e) => setBusinessLine(e.target.value)}
          placeholder="业务线（例如：电商）"
          className="w-full rounded-xl border border-primary-200 px-3 py-2 text-sm outline-none focus:border-primary-400"
        />
        <input
          type="date"
          value={interviewAt}
          onChange={(e) => setInterviewAt(e.target.value)}
          className="w-full rounded-xl border border-primary-200 px-3 py-2 text-sm outline-none focus:border-primary-400"
        />
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="补充说明（可选）"
          className="h-20 w-full resize-none rounded-xl border border-primary-200 px-3 py-2 text-sm outline-none focus:border-primary-400"
        />
      </div>

      <div className="mt-3 flex items-center justify-between">
        <p className="text-xs text-primary-600">已选 {files.length} 张图片</p>
        <button
          type="button"
          onClick={() => void onUpload()}
          disabled={uploading || files.length === 0}
          className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading ? '上传中...' : '上传并创建批次'}
        </button>
      </div>
    </section>
  )

  const batchesPanel = (
    <section className="rounded-2xl border border-primary-100 bg-white p-3 md:p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-primary-900">批次与处理任务</h3>
        <button
          type="button"
          onClick={() => void loadBatches()}
          className="rounded-lg border border-primary-200 px-2 py-1 text-xs text-primary-700 hover:bg-primary-50"
        >
          刷新
        </button>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2">
        <NavLink
          to="/experience/batches"
          className={() =>
            `rounded-lg px-3 py-2 text-center text-sm font-medium transition ${
              isBatchActive
                ? 'bg-primary-600 text-white'
                : 'bg-primary-50 text-primary-700 hover:bg-primary-100'
            }`
          }
        >
          批次详情
        </NavLink>
        <NavLink
          to="/experience/hot-questions"
          className={() =>
            `rounded-lg px-3 py-2 text-center text-sm font-medium transition ${
              isHotQuestionsActive
                ? 'bg-primary-600 text-white'
                : 'bg-primary-50 text-primary-700 hover:bg-primary-100'
            }`
          }
        >
          高频题
        </NavLink>
      </div>

      <div className="space-y-2">
        {batches.map((row) => {
          const batchPath = `/experience/batches/${row.id}`
          const isActive = location.pathname === batchPath || location.pathname.startsWith(`${batchPath}/`)
          const isRunning = (tasksByBatch[row.id] || []).some((task) => isTaskActive(task.status))
          return (
            <NavLink
              key={row.id}
              to={batchPath}
              className={() =>
                `block w-full rounded-xl border px-3 py-2 text-left transition ${
                  isActive
                    ? 'border-primary-400 bg-primary-50'
                    : 'border-primary-100 bg-white hover:bg-primary-50/70'
                }`
              }
            >
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-medium text-primary-900">
                  {row.company || '未标注公司'} · {row.business_line || '未标注业务线'}
                </p>
                <span className={`rounded-full px-2 py-0.5 text-[11px] ${statusClass(row.status)}`}>
                  {statusLabel(row.status)}
                </span>
              </div>
              <p className="mt-1 text-xs text-primary-600">
                图片 {row.image_count} · 题目 {row.question_count} · {formatDateTime(row.created_at)}
              </p>
              {isRunning && <p className="mt-1 text-[11px] text-amber-600">当前有任务在队列中</p>}
            </NavLink>
          )
        })}
      </div>

      {batchesLoading && <p className="mt-3 text-xs text-primary-600">批次加载中...</p>}
      {!batchesLoading && batches.length === 0 && (
        <p className="mt-3 rounded-xl border border-dashed border-primary-200 bg-primary-50/60 p-3 text-xs text-primary-700">
          还没有批次，先上传截图创建一个批次。
        </p>
      )}
    </section>
  )

  return (
    <div className="h-screen w-screen overflow-hidden p-3 md:p-5">
      <div className="mx-auto flex h-full max-w-[1400px] gap-3">
        {/* Mobile menu toggle could go here */}
        <aside className="flex w-80 flex-col gap-4 overflow-auto rounded-3xl border border-primary-100 bg-primary-50 p-4">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-bold text-primary-900">Coach App</h1>
            <NavLink
              to="/"
              className="rounded-lg border border-primary-200 px-2 py-1 text-xs text-primary-700 hover:bg-primary-100"
            >
              返回首页
            </NavLink>
          </div>

          {/* Mobile tabs */}
          <div className="grid grid-cols-2 gap-2 border-b border-primary-100 bg-white p-2 md:hidden">
            {MOBILE_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setMobileTab(tab.key)}
                className={`rounded-lg px-2 py-2 text-sm ${
                  mobileTab === tab.key ? 'bg-primary-600 text-white' : 'bg-primary-50 text-primary-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Desktop sidebar content */}
          <div className="hidden space-y-4 md:block">
            {uploadPanel}
            {batchesPanel}
          </div>

          {/* Mobile sidebar content */}
          <div className="space-y-4 md:hidden">
            {mobileTab === 'upload' && uploadPanel}
            {mobileTab === 'batches' && batchesPanel}
          </div>
        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col rounded-3xl border border-primary-100 bg-primary-50/60 backdrop-blur-sm">
          <header className="flex items-center justify-between border-b border-primary-100 bg-white/90 px-4 py-3">
            <div>
              <h2 className="text-base font-semibold text-primary-900">面经挖掘</h2>
              <p className="text-xs text-primary-600">
                {isBatchActive ? '批次详情' : isHotQuestionsActive ? '高频题' : '面经工作台'}
              </p>
            </div>
          </header>

          {error && <div className="px-4 py-2 text-xs text-red-600">{error}</div>}

          <div className="flex-1 overflow-auto p-4">
            <Outlet context={{ onProcessBatch }} />
          </div>
        </main>
      </div>

      {previewingFile && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-primary-950/55 p-4 backdrop-blur-sm"
          onClick={() => setPreviewingFileId(null)}
        >
          <div
            className="w-full max-w-3xl rounded-3xl border border-primary-100 bg-white p-4 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-primary-900">{previewingFile.file.name}</p>
                <p className="text-xs text-primary-600">
                  {Math.max(1, Math.round(previewingFile.file.size / 1024))} KB
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => removeFile(previewingFile.id)}
                  className="rounded-xl border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50"
                >
                  移除
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewingFileId(null)}
                  className="rounded-xl border border-primary-200 px-3 py-1.5 text-xs font-medium text-primary-700 hover:bg-primary-50"
                >
                  关闭
                </button>
              </div>
            </div>
            <div className="overflow-hidden rounded-2xl border border-primary-100 bg-primary-50/60">
              <img
                src={previewingFile.previewUrl}
                alt={previewingFile.file.name}
                className="max-h-[70vh] w-full object-contain"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
