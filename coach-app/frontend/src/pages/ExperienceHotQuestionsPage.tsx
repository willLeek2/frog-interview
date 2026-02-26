import { useCallback, useEffect, useState } from 'react'

import {
  listExperienceHotQuestions,
  getExperienceClusterDetail,
} from '../lib/api'
import type {
  ExperienceHotQuestion,
  ExperienceClusterDetail,
} from '../lib/types'

function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

export default function ExperienceHotQuestionsPage() {
  const [hotQuestions, setHotQuestions] = useState<ExperienceHotQuestion[]>([])
  const [loading, setLoading] = useState(false)
  const [hotDays, setHotDays] = useState(180)
  const [hotCompany, setHotCompany] = useState('')
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null)
  const [clusterDetail, setClusterDetail] = useState<ExperienceClusterDetail | null>(null)
  const [clusterLoading, setClusterLoading] = useState(false)

  const loadHotQuestions = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await listExperienceHotQuestions({
        days: hotDays,
        company: hotCompany.trim() || undefined,
        limit: 30,
      })
      setHotQuestions(rows)
      // Auto-select first cluster if none selected
      if (rows.length > 0 && !selectedClusterId) {
        setSelectedClusterId(rows[0].cluster_id)
      }
    } finally {
      setLoading(false)
    }
  }, [hotDays, hotCompany, selectedClusterId])

  const loadClusterDetail = useCallback(async (clusterId: string) => {
    setClusterLoading(true)
    try {
      const data = await getExperienceClusterDetail(clusterId, 200)
      setClusterDetail(data)
    } finally {
      setClusterLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadHotQuestions()
  }, [loadHotQuestions])

  useEffect(() => {
    if (!selectedClusterId) return
    void loadClusterDetail(selectedClusterId)
  }, [selectedClusterId, loadClusterDetail])

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {/* Hot questions list */}
      <section className="rounded-2xl border border-primary-100 bg-white p-4">
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

        <div className="space-y-2 max-h-[600px] overflow-auto pr-1">
          {hotQuestions.map((item, idx) => {
            const active = item.cluster_id === selectedClusterId
            return (
              <button
                key={item.cluster_id}
                type="button"
                onClick={() => setSelectedClusterId(item.cluster_id)}
                className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                  active
                    ? 'border-primary-400 bg-primary-50'
                    : 'border-primary-100 bg-white hover:bg-primary-50/70'
                }`}
              >
                <p className="text-xs text-primary-500">#{idx + 1}</p>
                <p className="mt-1 line-clamp-2 text-sm font-medium text-primary-900">
                  {item.canonical_question}
                </p>
                <p className="mt-1 text-xs text-primary-600">
                  频次 {item.total_count} · 最近 {formatDateTime(item.last_seen_at)}
                </p>
              </button>
            )
          })}
        </div>

        {loading && <p className="mt-3 text-xs text-primary-600">高频题加载中...</p>}
        {!loading && hotQuestions.length === 0 && (
          <p className="mt-3 rounded-xl border border-dashed border-primary-200 bg-primary-50/60 p-3 text-xs text-primary-700">
            暂无统计结果，先处理一些批次。
          </p>
        )}
      </section>

      {/* Cluster detail */}
      <section className="rounded-2xl border border-primary-100 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-primary-900">题簇详情</h3>

        {!selectedClusterId && (
          <p className="text-sm text-primary-600">请从左侧选择一个题簇查看详情。</p>
        )}

        {selectedClusterId && clusterLoading && (
          <p className="text-sm text-primary-600">加载中...</p>
        )}

        {clusterDetail && (
          <div className="space-y-4">
            <div className="rounded-xl bg-primary-50 p-3">
              <p className="text-sm font-medium text-primary-900">
                {clusterDetail.canonical_question}
              </p>
              <p className="mt-2 text-xs text-primary-600">
                出现 {clusterDetail.total_count} 次 · 最近{' '}
                {formatDateTime(clusterDetail.last_seen_at)}
              </p>
            </div>

            {/* Variants */}
            <div className="rounded-xl border border-primary-100 p-3">
              <p className="mb-2 text-xs font-semibold text-primary-800">
                同义问法 ({clusterDetail.variants.length})
              </p>
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

            {/* Source batches */}
            <div className="rounded-xl border border-primary-100 p-3">
              <p className="mb-2 text-xs font-semibold text-primary-800">
                来源批次 ({clusterDetail.source_batches.length})
              </p>
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
          </div>
        )}
      </section>
    </div>
  )
}
