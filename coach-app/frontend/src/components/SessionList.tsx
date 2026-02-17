import type { Session } from '../lib/types'

interface Props {
  sessions: Session[]
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
}

export default function SessionList({ sessions, activeId, onSelect, onCreate }: Props) {
  return (
    <div className="mt-4 rounded-2xl border border-primary-100 bg-white p-3">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-primary-800">会话列表</h3>
        <button
          onClick={onCreate}
          className="rounded-lg bg-primary-500 px-2 py-1 text-xs font-medium text-white hover:bg-primary-600"
        >
          新建
        </button>
      </div>

      <div className="max-h-[45vh] space-y-2 overflow-auto pr-1">
        {sessions.map((session) => {
          const active = session.id === activeId
          return (
            <button
              key={session.id}
              onClick={() => onSelect(session.id)}
              className={`w-full rounded-xl px-3 py-2 text-left text-sm ${
                active ? 'bg-primary-100 text-primary-900' : 'bg-primary-50 text-primary-700 hover:bg-primary-100'
              }`}
            >
              <p className="truncate">{session.title || '未命名会话'}</p>
              <p className="mt-1 text-[11px] opacity-70">{new Date(session.updated_at).toLocaleString()}</p>
            </button>
          )
        })}

        {sessions.length === 0 && <p className="text-xs text-primary-600">暂无会话，点击“新建”开始。</p>}
      </div>
    </div>
  )
}
