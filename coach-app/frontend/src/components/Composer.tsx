import { useState } from 'react'

import VoiceInput from './VoiceInput'

interface Props {
  disabled?: boolean
  placeholder?: string
  quickActions?: Array<{ label: string; prompt: string }>
  onSend: (content: string) => Promise<void>
}

export default function Composer({ disabled = false, placeholder, quickActions = [], onSend }: Props) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)

  const submitContent = async (raw: string) => {
    const content = raw.trim()
    if (!content || sending || disabled) return
    setSending(true)
    try {
      await onSend(content)
      setText('')
    } finally {
      setSending(false)
    }
  }

  const submit = async () => submitContent(text)

  return (
    <div className="border-t border-primary-100 bg-white p-3">
      {quickActions.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {quickActions.map((item) => (
            <button
              key={item.label}
              type="button"
              disabled={disabled || sending}
              onClick={async () => {
                setText(item.prompt)
                await submitContent(item.prompt)
              }}
              className="rounded-lg border border-primary-200 px-2 py-1 text-xs text-primary-700 hover:bg-primary-50 disabled:opacity-50"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      <div className="mb-2 flex items-center justify-between">
        <VoiceInput
          onText={(voiceText) => {
            setText((prev) => (prev ? `${prev}\n${voiceText}` : voiceText))
          }}
        />
        <div className="flex items-center gap-3">
          <span className="text-xs text-primary-500">⌘/Ctrl + Enter 发送</span>
          <button
            onClick={submit}
            disabled={disabled || sending}
            className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {sending ? '发送中...' : '发送'}
          </button>
        </div>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault()
            void submit()
          }
        }}
        placeholder={placeholder || '输入问题，支持追问...'}
        className="h-24 w-full resize-none rounded-xl border border-primary-200 p-3 text-sm outline-none focus:border-primary-400"
      />
    </div>
  )
}
