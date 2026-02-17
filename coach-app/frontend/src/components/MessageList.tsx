import type { Message } from '../lib/types'

interface Props {
  messages: Message[]
  loading?: boolean
}

export default function MessageList({ messages, loading = false }: Props) {
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
                    <a
                      key={`${c.url || c.title}-${idx}`}
                      href={c.url || '#'}
                      target="_blank"
                      rel="noreferrer"
                      className="block truncate underline decoration-primary-300 underline-offset-2"
                    >
                      {c.title || c.url || '未命名来源'}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })}

      {loading && (
        <div className="text-sm text-primary-700">
          <span className="animate-pulse">正在生成回答...</span>
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
