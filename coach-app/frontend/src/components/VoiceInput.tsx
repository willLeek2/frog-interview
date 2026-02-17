import { useMemo, useRef, useState } from 'react'

import { transcribeAudio } from '../lib/api'

declare global {
  interface Window {
    webkitSpeechRecognition?: any
    SpeechRecognition?: any
  }
}

interface Props {
  onText: (text: string) => void
}

export default function VoiceInput({ onText }: Props) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const RecognitionCtor = useMemo(() => window.SpeechRecognition || window.webkitSpeechRecognition, [])

  const startBrowserRecognition = () => {
    setError(null)
    if (!RecognitionCtor) return
    const recognition = new RecognitionCtor()
    recognition.lang = 'zh-CN'
    recognition.interimResults = false
    recognition.maxAlternatives = 1
    recognition.onstart = () => setRecording(true)
    recognition.onend = () => setRecording(false)
    recognition.onerror = () => {
      setRecording(false)
      setError('浏览器语音识别失败，请使用上传转写。')
    }
    recognition.onresult = (event: any) => {
      const text = event.results?.[0]?.[0]?.transcript || ''
      if (text) onText(text)
    }
    recognition.start()
  }

  const onUploadAudio = async (file: File) => {
    setBusy(true)
    setError(null)
    try {
      const text = await transcribeAudio(file)
      if (text) onText(text)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="space-y-2">
      {RecognitionCtor ? (
        <button
          type="button"
          onClick={startBrowserRecognition}
          className="rounded-lg border border-primary-200 px-3 py-1 text-xs text-primary-700 hover:bg-primary-50"
        >
          {recording ? '识别中...' : '语音输入'}
        </button>
      ) : (
        <label className="inline-flex cursor-pointer items-center rounded-lg border border-primary-200 px-3 py-1 text-xs text-primary-700 hover:bg-primary-50">
          上传音频转写
          <input
            ref={inputRef}
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) {
                void onUploadAudio(file)
              }
            }}
          />
        </label>
      )}

      {busy && <p className="text-xs text-primary-700">音频转写中...</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  )
}
