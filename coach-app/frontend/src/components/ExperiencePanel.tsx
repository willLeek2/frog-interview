import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  createExperienceBatch,
  deleteExperienceQuestion,
  getExperienceBatchDetail,
  getExperienceClusterDetail,
  getExperienceTask,
  listAlgorithmQuestions,
  listExperienceBatchTasks,
  listExperienceBatches,
  listExperienceHotQuestions,
  processExperienceBatch,
} from '../lib/api'
import type {
  AlgorithmQuestion,
  ExperienceBatch,
  ExperienceBatchDetail,
  ExperienceClusterDetail,
  ExperienceHotQuestion,
  ExperienceProcessTask,
  ExperienceTaskStatus,
} from '../lib/types'

type MobileTab = 'upload' | 'batches' | 'hot' | 'algorithm'

const MOBILE_TABS: Array<{ key: MobileTab; label: string }> = [
  { key: 'upload', label: '上传' },
  { key: 'batches', label: '批次' },
  { key: 'hot', label: '高频题' },
  { key: 'algorithm', label: '算法题' },
]

function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
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

function isTaskActive(status: ExperienceTaskStatus): boolean {
  return status === 'queued' || status === 'running'
}

export default function ExperiencePanel() {
  const [mobileTab, setMobileTab] = useState<MobileTab>('upload')
  const [files, setFiles] = useState<File[]>([])
  const [company, setCompany] = useState('')
  const [businessLine, setBusinessLine] = useState('')
  const [interviewAt, setInterviewAt] = useState('')
  const [notes, setNotes] = useState('')

  const [batches, setBatches] = useState<ExperienceBatch[]>([])
  const [batchesLoading, setBatchesLoading] = useState(false)
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)
  const [batchDetail, setBatchDetail] = useState<ExperienceBatchDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [tasksByBatch, setTasksByBatch] = useState<Record<string, ExperienceProcessTask[]>>({})
  const [pollingTaskMap, setPollingTaskMap] = useState<Record<string, string>>({})

  const [hotQuestions, setHotQuestions] = useState<ExperienceHotQuestion[]>([])
  const [hotLoading, setHotLoading] = useState(false)
  const [hotDays, setHotDays] = useState(180)
  const [hotCompany, setHotCompany] = useState('')
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null)
  const [clusterDetail, setClusterDetail] = useState<ExperienceClusterDetail | null>(null)
  const [clusterLoading, setClusterLoading] = useState(false)

  const [algorithmQuestions, setAlgorithmQuestions] = useState<AlgorithmQuestion[]>([])
  const [algorithmLoading, setAlgorithmLoading] = useState(false)

  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const selectedBatch = useMemo(
    () => batches.find((item) => item.id === selectedBatchId) ?? null,
    [batches, selectedBatchId],
  )
  const selectedBatchTasks = selectedBatchId ? tasksByBatch[selectedBatchId] || [] : []

  const loadBatches = useCallback(async () => {
    setBatchesLoading(true)
    try {
      const rows = await listExperienceBatches()
      setBatches(rows)
      setSelectedBatchId((prev) => prev || rows[0]?.id || null)
    } finally {
      setBatchesLoading(false)
    }
  }, [])

  const loadBatchDetail = useCallback(async (batchId: string) => {
    setDetailLoading(true)
    try {
      const data = await getExperienceBatchDetail(batchId)
      setBatchDetail(data)
    } finally {
      setDetailLoading(false)
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

  const loadHotQuestions = useCallback(async () => {
    setHotLoading(true)
    try {
      const rows = await listExperienceHotQuestions({
        days: hotDays,
        company: hotCompany.trim() || undefined,
        limit: 30,
      })
      setHotQuestions(rows)
      if (rows.length === 0) {
        setSelectedClusterId(null)
        setClusterDetail(null)
        return
      }
      setSelectedClusterId((prev) => {
        const stillExists = rows.some((row) => row.cluster_id === prev)
        return stillExists ? prev : rows[0].cluster_id
      })
    } finally {
      setHotLoading(false)
    }
  }, [hotCompany, hotDays])

  const loadClusterDetail = useCallback(async (clusterId: string) => {
    setClusterLoading(true)
    try {
      const data = await getExperienceClusterDetail(clusterId, 200)
      setClusterDetail(data)
    } finally {
      setClusterLoading(false)
    }
  }, [])

  const loadAlgorithmQuestions = useCallback(async () => {
    setAlgorithmLoading(true)
    try {
      const rows = await listAlgorithmQuestions({ limit: 100 })
      setAlgorithmQuestions(rows)
    } finally {
      setAlgorithmLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadBatches()
    void loadHotQuestions()
    void loadAlgorithmQuestions()
  }, [loadBatches, loadHotQuestions, loadAlgorithmQuestions])

  useEffect(() => {
    if (!selectedBatchId) return
    void loadBatchDetail(selectedBatchId)
    void loadBatchTasks(selectedBatchId)
  }, [selectedBatchId, loadBatchDetail, loadBatchTasks])

  useEffect(() => {
    if (!selectedClusterId) return
    void loadClusterDetail(selectedClusterId)
  }, [selectedClusterId, loadClusterDetail])

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
          void loadHotQuestions()
          if (selectedBatchId && finishedBatchIds.has(selectedBatchId)) {
            void loadBatchDetail(selectedBatchId)
            void loadBatchTasks(selectedBatchId)
          }
        }
      })()
    }, 2500)

    return () => window.clearInterval(timer)
  }, [loadBatchDetail, loadBatchTasks, loadBatches, loadHotQuestions, pollingTaskMap, selectedBatchId])

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
      await loadBatches()
      setSelectedBatchId(row.id)
      setMobileTab('batches')
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

  const onSelectCluster = (clusterId: string) => {
    setSelectedClusterId(clusterId)
    setMobileTab('hot')
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
      file.type.startsWith('image/')
    )
    if (droppedFiles.length > 0) {
      setFiles((prev) => [...prev, ...droppedFiles].slice(0, 20))
    }
  }, [])

  const handleDeleteQuestion = useCallback(async (questionId: string) => {
    if (!selectedBatchId) return
    if (!confirm('确定要删除这道题目吗？')) return
    try {
      await deleteExperienceQuestion(selectedBatchId, questionId)
      await loadBatchDetail(selectedBatchId)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [selectedBatchId, loadBatchDetail])

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
            onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, 20))}
          />
        </label>
      </div>

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

      <div className="space-y-2">
        {batches.map((row) => {
          const active = row.id === selectedBatchId
          const isRunning = (tasksByBatch[row.id] || []).some((task) => isTaskActive(task.status))
          return (
            <button
              key={row.id}
              type="button"
              onClick={() => setSelectedBatchId(row.id)}
              className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                active ? 'border-primary-400 bg-primary-50' : 'border-primary-100 bg-white hover:bg-primary-50/70'
              }`}
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
            </button>
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

  const algorithmPanel = (
    <section className="rounded-2xl border border-primary-100 bg-white p-3 md:p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-primary-900">算法题（手撕/编程）</h3>
        <button
          type="button"
          onClick={() => void loadAlgorithmQuestions()}
          className="rounded-lg border border-primary-200 px-2 py-1 text-xs text-primary-700 hover:bg-primary-50"
        >
          刷新
        </button>
      </div>

      <div className="space-y-2">
        {algorithmQuestions.map((item, idx) => (
          <div
            key={item.id}
            className="rounded-xl border border-primary-100 bg-white px-3 py-2"
          >
            <p className="text-xs text-primary-500">#{idx + 1}</p>
            <p className="mt-1 text-sm font-medium text-primary-900">{item.question_text}</p>
            <p className="mt-1 text-xs text-primary-600">
              {item.company || '未标注公司'} · {item.business_line || '未标注业务线'}
            </p>
          </div>
        ))}
      </div>

      {algorithmLoading && <p className="mt-3 text-xs text-primary-600">算法题加载中...</p>}
      {!algorithmLoading && algorithmQuestions.length === 0 && (
        <p className="mt-3 rounded-xl border border-dashed border-primary-200 bg-primary-50/60 p-3 text-xs text-primary-700">
          暂无算法题，处理面经批次后会自动识别包含"手撕"、"算法题"等字样的题目。
        </p>
      )}
    </section>
  )

  const hotPanel = (
    <section className="rounded-2xl border border-primary-100 bg-white p-3 md:p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-primary-900">高频题（题簇）</h3>
        <button
          type="button"
          onClick={() => void loadHotQuestions()}
          className="rounded-lg border border-primary-200 px-2 py-1 text-xs text-primary-700 hover:bg-primary-50"
        >
          刷新
        </button>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2">
        <select
          value={hotDays}
          onChange={(e) => setHotDays(Number(e.target.value))}
          className="rounded-xl border border-primary-200 px-2 py-2 text-sm outline-none focus:border-primary-400"
        >
          <option value={30}>近 30 天</option>
          <option value={90}>近 90 天</option>
          <option value={180}>近半年</option>
        </select>
        <input
          value={hotCompany}
          onChange={(e) => setHotCompany(e.target.value)}
          placeholder="按公司过滤"
          className="rounded-xl border border-primary-200 px-3 py-2 text-sm outline-none focus:border-primary-400"
        />
      </div>

      <button
        type="button"
        onClick={() => void loadHotQuestions()}
        className="mb-3 w-full rounded-xl bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700"
      >
        应用过滤
      </button>

      <div className="space-y-2">
        {hotQuestions.map((item, idx) => {
          const active = item.cluster_id === selectedClusterId
          return (
            <button
              key={item.cluster_id}
              type="button"
              onClick={() => onSelectCluster(item.cluster_id)}
              className={`w-full rounded-xl border px-3 py-2 text-left ${
                active ? 'border-primary-400 bg-primary-50' : 'border-primary-100 bg-white hover:bg-primary-50/70'
              }`}
            >
              <p className="text-xs text-primary-500">#{idx + 1}</p>
              <p className="mt-1 line-clamp-2 text-sm font-medium text-primary-900">{item.canonical_question}</p>
              <p className="mt-1 text-xs text-primary-600">
                频次 {item.total_count} · 最近 {formatDateTime(item.last_seen_at)}
              </p>
            </button>
          )
        })}
      </div>

      {hotLoading && <p className="mt-3 text-xs text-primary-600">高频题加载中...</p>}
      {!hotLoading && hotQuestions.length === 0 && (
        <p className="mt-3 rounded-xl border border-dashed border-primary-200 bg-primary-50/60 p-3 text-xs text-primary-700">
          暂无统计结果，先处理一些批次。
        </p>
      )}
    </section>
  )

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="grid grid-cols-4 gap-2 border-b border-primary-100 bg-white p-2 md:hidden">
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

      {error && <div className="px-3 pt-2 text-xs text-rose-600 md:px-4">{error}</div>}

      <div className="flex-1 overflow-auto p-3 md:p-4">
        <div className="space-y-3 md:hidden">
          {mobileTab === 'upload' && uploadPanel}
          {mobileTab === 'batches' && (
            <>
              {batchesPanel}
              <section className="rounded-2xl border border-primary-100 bg-white p-3">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-primary-900">批次详情</h3>
                  <button
                    type="button"
                    disabled={!selectedBatchId}
                    onClick={() => selectedBatchId && void onProcessBatch(selectedBatchId)}
                    className="rounded-lg bg-primary-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
                  >
                    处理当前批次
                  </button>
                </div>
                {!selectedBatchId && <p className="text-xs text-primary-600">请选择一个批次。</p>}
                {selectedBatchId && detailLoading && <p className="text-xs text-primary-600">加载中...</p>}
                {selectedBatch && (
                  <div className="mb-2 rounded-xl bg-primary-50 p-2 text-xs text-primary-700">
                    状态 {statusLabel(selectedBatch.status)} · 图片 {selectedBatch.image_count} · 题目{' '}
                    {selectedBatch.question_count}
                  </div>
                )}
                {selectedBatchTasks.length > 0 && (
                  <div className="mb-3 space-y-2">
                    {selectedBatchTasks.slice(0, 5).map((task) => (
                      <div key={task.id} className="rounded-xl border border-primary-100 px-2 py-1.5 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="text-primary-700">{task.id.slice(0, 8)}</span>
                          <span className={`rounded-full px-2 py-0.5 ${statusClass(task.status)}`}>
                            {statusLabel(task.status)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {batchDetail?.questions && batchDetail.questions.length > 0 ? (
                  <div className="space-y-2">
                    {batchDetail.questions.slice(0, 8).map((question) => (
                      <div key={question.id} className="group relative rounded-xl border border-primary-100 px-2 py-1.5 text-xs">
                        <button
                          type="button"
                          onClick={() => handleDeleteQuestion(question.id)}
                          className="absolute right-1 top-1 rounded px-1 text-primary-400 hover:bg-rose-50 hover:text-rose-600"
                          title="删除题目"
                        >
                          ×
                        </button>
                        <p className="pr-4 text-primary-900">{question.question_text}</p>
                        {question.extra?.is_algorithm === true && (
                          <span className="mt-1 inline-block rounded bg-amber-100 px-1 py-0.5 text-[10px] text-amber-700">算法题</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-primary-600">当前批次还没有题目结果。</p>
                )}
              </section>
            </>
          )}
          {mobileTab === 'hot' && (
            <>
              {hotPanel}
              <section className="rounded-2xl border border-primary-100 bg-white p-3">
                <h3 className="mb-2 text-sm font-semibold text-primary-900">题簇详情</h3>
                {!selectedClusterId && <p className="text-xs text-primary-600">请选择一个题簇。</p>}
                {selectedClusterId && clusterLoading && <p className="text-xs text-primary-600">加载中...</p>}
                {clusterDetail && (
                  <>
                    <p className="rounded-xl bg-primary-50 p-2 text-sm text-primary-900">
                      {clusterDetail.canonical_question}
                    </p>
                    <p className="mt-2 text-xs text-primary-600">
                      频次 {clusterDetail.total_count} · 最近 {formatDateTime(clusterDetail.last_seen_at)}
                    </p>
                    <div className="mt-3 space-y-2">
                      {clusterDetail.variants.slice(0, 10).map((item) => (
                        <div key={item.normalized_question} className="rounded-xl border border-primary-100 p-2">
                          <p className="text-xs font-medium text-primary-900">{item.sample_question}</p>
                          <p className="mt-1 text-[11px] text-primary-600">出现 {item.count} 次</p>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </section>
            </>
          )}
          {mobileTab === 'algorithm' && algorithmPanel}
        </div>

        <div className="hidden gap-4 md:grid md:grid-cols-[360px_minmax(0,1fr)]">
          <div className="space-y-4">
            {uploadPanel}
            {batchesPanel}
            {algorithmPanel}
          </div>

          <div className="space-y-4">
            <section className="rounded-2xl border border-primary-100 bg-white p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-primary-900">批次详情</h3>
                <button
                  type="button"
                  disabled={!selectedBatchId}
                  onClick={() => selectedBatchId && void onProcessBatch(selectedBatchId)}
                  className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
                >
                  处理当前批次
                </button>
              </div>
              {!selectedBatchId && <p className="text-sm text-primary-600">请选择左侧批次。</p>}
              {selectedBatchId && detailLoading && <p className="text-sm text-primary-600">加载中...</p>}
              {selectedBatch && (
                <div className="mb-3 grid grid-cols-3 gap-2 rounded-xl bg-primary-50 p-3 text-xs text-primary-700">
                  <p>状态：{statusLabel(selectedBatch.status)}</p>
                  <p>图片：{selectedBatch.image_count}</p>
                  <p>题目：{selectedBatch.question_count}</p>
                </div>
              )}

              {selectedBatchTasks.length > 0 && (
                <div className="mb-3 rounded-xl border border-primary-100 p-3">
                  <p className="mb-2 text-xs font-semibold text-primary-800">任务历史</p>
                  <div className="space-y-2">
                    {selectedBatchTasks.slice(0, 8).map((task) => (
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

              <div className="space-y-2">
                {batchDetail?.questions?.slice(0, 12).map((question) => (
                  <div key={question.id} className="group relative rounded-xl border border-primary-100 p-2">
                    <button
                      type="button"
                      onClick={() => handleDeleteQuestion(question.id)}
                      className="absolute right-1 top-1 rounded p-1 text-primary-400 opacity-0 transition hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
                      title="删除题目"
                    >
                      ×
                    </button>
                    <p className="text-sm text-primary-900">{question.question_text}</p>
                    <p className="mt-1 text-xs text-primary-600">
                      tags: {question.topic_tags.join(' / ') || '-'} · 置信度 {question.confidence.toFixed(2)}
                      {question.extra?.is_algorithm === true && (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-amber-700">算法题</span>
                      )}
                    </p>
                  </div>
                ))}
              </div>
              {batchDetail && batchDetail.questions.length === 0 && (
                <p className="text-sm text-primary-600">当前批次尚未抽取出题目。</p>
              )}
            </section>

            <div className="grid gap-4 xl:grid-cols-2">
              {hotPanel}

              <section className="rounded-2xl border border-primary-100 bg-white p-4">
                <h3 className="mb-3 text-sm font-semibold text-primary-900">题簇详情</h3>
                {!selectedClusterId && <p className="text-sm text-primary-600">请选择一个高频题簇。</p>}
                {selectedClusterId && clusterLoading && <p className="text-sm text-primary-600">加载中...</p>}
                {clusterDetail && (
                  <>
                    <p className="rounded-xl bg-primary-50 p-3 text-sm font-medium text-primary-900">
                      {clusterDetail.canonical_question}
                    </p>
                    <p className="mt-2 text-xs text-primary-600">
                      出现 {clusterDetail.total_count} 次 · 最近 {formatDateTime(clusterDetail.last_seen_at)}
                    </p>

                    <div className="mt-3 rounded-xl border border-primary-100 p-3">
                      <p className="mb-2 text-xs font-semibold text-primary-800">同义问法</p>
                      <div className="max-h-48 space-y-2 overflow-auto pr-1">
                        {clusterDetail.variants.map((item) => (
                          <div key={item.normalized_question} className="rounded-lg bg-primary-50/60 p-2">
                            <p className="text-xs text-primary-900">{item.sample_question}</p>
                            <p className="mt-1 text-[11px] text-primary-600">
                              计数 {item.count} · 最近 {formatDateTime(item.last_seen_at)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="mt-3 rounded-xl border border-primary-100 p-3">
                      <p className="mb-2 text-xs font-semibold text-primary-800">来源批次</p>
                      <div className="max-h-40 space-y-2 overflow-auto pr-1">
                        {clusterDetail.source_batches.map((item) => (
                          <div key={item.batch_id} className="rounded-lg bg-primary-50/60 p-2">
                            <p className="text-xs text-primary-900">
                              {item.company || '未标注公司'} · {item.business_line || '未标注业务线'}
                            </p>
                            <p className="mt-1 text-[11px] text-primary-600">
                              题目 {item.question_count} · 最近 {formatDateTime(item.last_seen_at)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </section>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
