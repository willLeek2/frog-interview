import type { ChatRunTask, Citation, Message } from '../lib/types'

interface Props {
  messages: Message[]
  loading?: boolean
  runTask?: ChatRunTask | null
  onOpenCitation?: (citation: Citation) => void
}

export default function MessageList({ messages, loading = false, runTask, onOpenCitation }: Props) {
  const recentEvents = runTask?.events?.slice(-4) || []

  return (
    <div className="flex-1 space-y-4 overflow-auto p-4">
      {messages.map((message) => {
        const isUser = message.role === 'user'
        return (
          <div key={message.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm md:max-w-[75%] ${
                isUser ? 'bg-primary-600 text-white' : 'bg-white text-primary-900 border border-primary-100'
              }`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>

              {!isUser && message.citations?.length > 0 && (
                <div className="mt-3 space-y-1 border-t border-primary-100 pt-2 text-xs text-primary-700">
                  <p className="font-semibold">参考来源</p>
                  {message.citations.slice(0, 8).map((c, idx) => (
                    <button
                      key={`${c.url || c.title}-${idx}`}
                      type="button"
                      onClick={() => onOpenCitation?.(c)}
                      className="block w-full truncate text-left underline decoration-primary-300 underline-offset-2"
                    >
                      {c.title || c.url || '未命名来源'}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })}

      {loading && (
        <div className="rounded-xl border border-primary-100 bg-white p-3 text-sm text-primary-700">
          <p className="animate-pulse">{runTask?.stage_label || '正在生成回答...'}</p>
          {recentEvents.length > 0 && (
            <div className="mt-2 space-y-1 text-xs text-primary-600">
              {recentEvents.map((event, idx) => (
                <p key={`${event.stage}-${event.at}-${idx}`}>
                  {event.label}
                  {event.detail ? ` · ${event.detail}` : ''}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {messages.length === 0 && !loading && (
        <div className="rounded-2xl border border-dashed border-primary-200 bg-white/70 p-4 text-sm text-primary-700">
          新会话已创建，输入你的问题开始复习。
        </div>
      )}
    </div>
  )
}
