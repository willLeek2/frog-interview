import { useEffect, useMemo, useRef, useState } from 'react'

import CitationViewer from './components/CitationViewer'
import Composer from './components/Composer'
import ExperiencePanel from './components/ExperiencePanel'
import FeatureMenu from './components/FeatureMenu'
import MessageList from './components/MessageList'
import SessionList from './components/SessionList'
import {
  createSession,
  deleteSession,
  getChatTask,
  getCitationContent,
  getIndexRebuildTask,
  getSessionDetail,
  listSessions,
  rebuildIndex,
  sendMessage,
} from './lib/api'
import type {
  ChatRunTask,
  Citation,
  CitationContent,
  FeatureType,
  IndexRebuildMode,
  IndexRebuildTask,
  Message,
  Session,
} from './lib/types'

const TITLES: Record<FeatureType, string> = {
  random: '随机抽题',
  explain: '解释知识点',
  quiz: '出题训练',
  experience: '面经挖掘',
}

const PLACEHOLDERS: Record<FeatureType, string> = {
  random: '例如：开始随机抽题（偏 MySQL / Redis / JUC）',
  explain: '例如：解释：MySQL MVCC 的实现原理',
  quiz: '例如：出题：JUC 并发，难度中等',
  experience: '面经挖掘模式不使用此输入框',
}

const QUICK_ACTIONS: Record<FeatureType, Array<{ label: string; prompt: string }>> = {
  random: [
    { label: '开始随机抽题', prompt: '开始随机抽题，优先高频考点。' },
    { label: '抽 JVM 题', prompt: '开始随机抽题，主题偏 JVM。' },
  ],
  explain: [
    { label: '解释 MVCC', prompt: '解释：MySQL MVCC' },
    { label: '解释并发锁', prompt: '解释：ReentrantLock 和 synchronized 的区别' },
  ],
  quiz: [
    { label: '出 JUC 题', prompt: '出题：JUC 并发，3 题，包含追问。' },
    { label: '出缓存题', prompt: '出题：Redis 缓存一致性，2 题，偏实战。' },
  ],
  experience: [],
}

export default function App() {
  const [feature, setFeature] = useState<FeatureType>('explain')
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sending, setSending] = useState(false)
  const [chatTask, setChatTask] = useState<ChatRunTask | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [indexTask, setIndexTask] = useState<IndexRebuildTask | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [citationOpen, setCitationOpen] = useState(false)
  const [citationLoading, setCitationLoading] = useState(false)
  const [citationError, setCitationError] = useState<string | null>(null)
  const [citationData, setCitationData] = useState<CitationContent | null>(null)
  const chatTaskPollerRef = useRef<number | null>(null)

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  )
  const isExperience = feature === 'experience'
  const isChatFeature = !isExperience

  const stopChatTaskPolling = () => {
    if (chatTaskPollerRef.current) {
      window.clearInterval(chatTaskPollerRef.current)
      chatTaskPollerRef.current = null
    }
  }

  const loadSessions = async (nextFeature: FeatureType) => {
    setError(null)
    const data = await listSessions(nextFeature)
    setSessions(data)
    if (data.length > 0) {
      setActiveSessionId(data[0].id)
    } else {
      setActiveSessionId(null)
      setMessages([])
    }
  }

  const loadSessionDetail = async (sessionId: string) => {
    setLoadingMessages(true)
    setError(null)
    try {
      const detail = await getSessionDetail(sessionId)
      setMessages(detail.messages)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoadingMessages(false)
    }
  }

  useEffect(() => {
    stopChatTaskPolling()
    setChatTask(null)
    if (isChatFeature) {
      void loadSessions(feature)
      return
    }
    setSessions([])
    setActiveSessionId(null)
    setMessages([])
  }, [feature])

  useEffect(() => {
    if (!isChatFeature || !activeSessionId) return
    stopChatTaskPolling()
    setChatTask(null)
    void loadSessionDetail(activeSessionId)
  }, [activeSessionId, isChatFeature])

  useEffect(() => {
    return () => {
      stopChatTaskPolling()
    }
  }, [])

  const onCreateSession = async () => {
    if (!isChatFeature) return
    setError(null)
    try {
      const session = await createSession(feature)
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(session.id)
      setMessages([])
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const onDeleteSession = async (sessionId: string) => {
    if (!isChatFeature) return
    if (!window.confirm('确认删除这个会话吗？删除后不可恢复。')) return
    setError(null)
    try {
      await deleteSession(sessionId)
      const refreshed = await listSessions(feature)
      setSessions(refreshed)
      if (activeSessionId === sessionId) {
        stopChatTaskPolling()
        setSending(false)
        setChatTask(null)
        if (refreshed.length > 0) {
          setActiveSessionId(refreshed[0].id)
          void loadSessionDetail(refreshed[0].id)
        } else {
          setActiveSessionId(null)
          setMessages([])
        }
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const pollChatTask = (taskId: string, sessionId: string, featureType: FeatureType) => {
    stopChatTaskPolling()
    chatTaskPollerRef.current = window.setInterval(async () => {
      try {
        const task = await getChatTask(taskId)
        setChatTask(task)
        if (task.status === 'completed') {
          stopChatTaskPolling()
          setSending(false)
          await loadSessionDetail(sessionId)
          const refreshed = await listSessions(featureType)
          setSessions(refreshed)
        } else if (task.status === 'failed') {
          stopChatTaskPolling()
          setSending(false)
          setError(task.error_message || '回答生成失败，请稍后重试。')
        }
      } catch (e) {
        stopChatTaskPolling()
        setSending(false)
        setError((e as Error).message)
      }
    }, 1200)
  }

  const onSend = async (content: string) => {
    if (!isChatFeature) return
    setError(null)
    let targetSessionId = activeSessionId
    const featureForSend = feature
    if (!targetSessionId) {
      const created = await createSession(featureForSend)
      setSessions((prev) => [created, ...prev])
      setActiveSessionId(created.id)
      targetSessionId = created.id
    }

    const optimistic: Message = {
      id: `local-${Date.now()}`,
      session_id: targetSessionId,
      role: 'user',
      content,
      citations: [],
      metadata: {},
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, optimistic])
    setSending(true)
    setChatTask(null)

    try {
      const queued = await sendMessage(targetSessionId, content)
      setChatTask({
        id: queued.task_id,
        session_id: queued.session_id,
        status: queued.status,
        stage: queued.stage,
        stage_label: queued.stage_label,
        events: [],
        metadata: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })
      pollChatTask(queued.task_id, targetSessionId, featureForSend)
    } catch (e) {
      setError((e as Error).message)
      setSending(false)
    }
  }

  const onOpenCitation = async (citation: Citation) => {
    setCitationOpen(true)
    setCitationLoading(true)
    setCitationError(null)
    setCitationData(null)
    try {
      const data = await getCitationContent({
        url: citation.url,
        title: citation.title,
        source: citation.source,
      })
      setCitationData(data)
    } catch (e) {
      setCitationError((e as Error).message)
    } finally {
      setCitationLoading(false)
    }
  }

  const onRebuildIndex = async (mode: IndexRebuildMode) => {
    setIndexing(true)
    setError(null)
    try {
      const { task_id } = await rebuildIndex(mode)
      // 开始轮询任务进度
      pollIndexTask(task_id)
    } catch (e) {
      setError((e as Error).message)
      setIndexing(false)
    }
  }

  const pollIndexTask = (taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const task = await getIndexRebuildTask(taskId)
        setIndexTask(task)
        if (task.status === 'completed' || task.status === 'failed') {
          clearInterval(interval)
          setIndexing(false)
          if (task.status === 'completed') {
            // 3 秒后自动清空任务展示
            setTimeout(() => setIndexTask(null), 5000)
          }
        }
      } catch (e) {
        clearInterval(interval)
        setIndexing(false)
        setError((e as Error).message)
      }
    }, 1000)
  }

  return (
    <div className="h-screen w-screen overflow-hidden p-3 md:p-5">
      <div className="mx-auto flex h-full max-w-[1400px] gap-3">
        <aside
          className={`fixed inset-y-3 left-3 z-20 w-72 rounded-3xl border border-primary-100 bg-primary-50 p-4 shadow-soft transition md:static md:translate-x-0 ${
            sidebarOpen ? 'translate-x-0' : '-translate-x-[120%]'
          }`}
        >
          <div className="mb-4 flex items-center justify-between">
            <h1 className="text-lg font-bold text-primary-900">Coach App</h1>
            <button className="md:hidden" onClick={() => setSidebarOpen(false)}>
              关闭
            </button>
          </div>

          <FeatureMenu
            current={feature}
            onChange={(value) => {
              setFeature(value)
              setSidebarOpen(false)
            }}
          />

          {isChatFeature ? (
            <SessionList
              sessions={sessions}
              activeId={activeSessionId}
              onSelect={(id) => {
                setActiveSessionId(id)
                setSidebarOpen(false)
              }}
              onCreate={() => {
                void onCreateSession()
              }}
              onDelete={(id) => {
                void onDeleteSession(id)
              }}
            />
          ) : (
            <div className="mt-4 rounded-2xl border border-primary-100 bg-white p-3 text-xs text-primary-700">
              面经挖掘模式已切换到右侧工作台，不使用聊天会话列表。
            </div>
          )}
        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col rounded-3xl border border-primary-100 bg-primary-50/60 backdrop-blur-sm">
          <header className="flex items-center justify-between border-b border-primary-100 bg-white/90 px-4 py-3">
            <div className="flex items-center gap-2">
              <button
                className="rounded-lg border border-primary-200 px-2 py-1 text-sm md:hidden"
                onClick={() => setSidebarOpen(true)}
              >
                菜单
              </button>
              <div>
                <h2 className="text-base font-semibold text-primary-900">{TITLES[feature]}</h2>
                <p className="text-xs text-primary-600">
                  {isExperience ? '面经工作台' : activeSession?.title || '未选择会话'}
                </p>
              </div>
            </div>

            {isChatFeature && (
              <div className="flex items-center gap-2">
                {/* 索引进度展示 */}
                {indexTask && (
                  <div className="mr-2 flex items-center gap-2 text-xs">
                    <div className="flex flex-col items-end">
                      <span className="text-primary-700">
                        {indexTask.mode === 'full' ? '全量重建' : '增量更新'}
                        {' · '}
                        {indexTask.status === 'running' && '处理中...'}
                        {indexTask.status === 'completed' && '完成'}
                        {indexTask.status === 'failed' && '失败'}
                      </span>
                      <span className="text-primary-500">
                        {indexTask.files_scanned}/{indexTask.files_total} 文件
                        {indexTask.mode === 'incremental' && indexTask.files_added + indexTask.files_updated > 0 && (
                          <>
                            {' · '}新增 {indexTask.files_added}
                            {' · '}更新 {indexTask.files_updated}
                          </>
                        )}
                        {' · '}{indexTask.chunks_indexed} chunks
                      </span>
                    </div>
                    {/* 进度条 */}
                    <div className="h-8 w-1 overflow-hidden rounded-full bg-primary-100">
                      <div
                        className={`w-full transition-all duration-300 ${
                          indexTask.status === 'failed' ? 'bg-red-400' : 'bg-green-500'
                        }`}
                        style={{
                          height: indexTask.files_total > 0
                            ? `${(indexTask.files_scanned / indexTask.files_total) * 100}%`
                            : '0%',
                        }}
                      />
                    </div>
                  </div>
                )}

                {/* 增量更新按钮 */}
                <button
                  onClick={() => void onRebuildIndex('incremental')}
                  disabled={indexing}
                  className="rounded-lg border border-primary-200 px-3 py-1 text-xs text-primary-700 hover:bg-primary-50 disabled:opacity-50"
                  title="只索引新增或变更的文件，速度快"
                >
                  {indexing && indexTask?.mode === 'incremental' ? '更新中...' : '更新索引'}
                </button>

                {/* 全量重建按钮 */}
                <button
                  onClick={() => void onRebuildIndex('full')}
                  disabled={indexing}
                  className="rounded-lg border border-primary-200 bg-primary-50 px-3 py-1 text-xs text-primary-700 hover:bg-primary-100 disabled:opacity-50"
                  title="清空后全部重新索引，最彻底"
                >
                  {indexing && indexTask?.mode === 'full' ? '重建中...' : '重建索引'}
                </button>
              </div>
            )}
          </header>

          {error && <div className="px-4 py-2 text-xs text-red-600">{error}</div>}

          {isExperience ? (
            <ExperiencePanel />
          ) : (
            <>
              <MessageList
                messages={messages}
                loading={loadingMessages || sending}
                runTask={chatTask}
                onOpenCitation={(citation) => {
                  void onOpenCitation(citation)
                }}
              />
              <Composer
                disabled={sending}
                placeholder={PLACEHOLDERS[feature]}
                quickActions={QUICK_ACTIONS[feature]}
                onSend={onSend}
              />
            </>
          )}
        </main>
      </div>
      <CitationViewer
        open={citationOpen}
        loading={citationLoading}
        error={citationError}
        data={citationData}
        onClose={() => setCitationOpen(false)}
      />
    </div>
  )
}
