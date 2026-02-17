import { useEffect, useMemo, useState } from 'react'

import Composer from './components/Composer'
import ExperiencePanel from './components/ExperiencePanel'
import FeatureMenu from './components/FeatureMenu'
import MessageList from './components/MessageList'
import SessionList from './components/SessionList'
import { createSession, getSessionDetail, listSessions, rebuildIndex, sendMessage } from './lib/api'
import type { FeatureType, Message, Session } from './lib/types'

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
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  )
  const isExperience = feature === 'experience'
  const isChatFeature = !isExperience

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
    void loadSessionDetail(activeSessionId)
  }, [activeSessionId, isChatFeature])

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

  const onSend = async (content: string) => {
    if (!isChatFeature) return
    let targetSessionId = activeSessionId
    if (!targetSessionId) {
      const created = await createSession(feature)
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

    try {
      const assistant = await sendMessage(targetSessionId, content)
      setMessages((prev) => [...prev, assistant])
      const refreshed = await listSessions(feature)
      setSessions(refreshed)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSending(false)
    }
  }

  const onRebuildIndex = async () => {
    setIndexing(true)
    setError(null)
    try {
      await rebuildIndex()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setIndexing(false)
    }
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
              <button
                onClick={() => void onRebuildIndex()}
                className="rounded-lg border border-primary-200 px-3 py-1 text-xs text-primary-700 hover:bg-primary-50"
              >
                {indexing ? '索引中...' : '重建索引'}
              </button>
            )}
          </header>

          {error && <div className="px-4 py-2 text-xs text-red-600">{error}</div>}

          {isExperience ? (
            <ExperiencePanel />
          ) : (
            <>
              <MessageList messages={messages} loading={loadingMessages || sending} />
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
    </div>
  )
}
