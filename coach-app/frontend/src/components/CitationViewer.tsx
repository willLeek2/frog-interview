import type { ReactNode } from 'react'

import type { CitationContent } from '../lib/types'

interface Props {
  open: boolean
  loading: boolean
  error: string | null
  data: CitationContent | null
  onClose: () => void
}

function renderInline(text: string): ReactNode[] {
  const tokens = text.split(/(`[^`]+`|\[[^\]]+\]\([^)]+\))/g)
  return tokens
    .filter(Boolean)
    .map((token, idx) => {
      if (token.startsWith('`') && token.endsWith('`')) {
        return (
          <code key={`code-${idx}`} className="rounded bg-primary-100 px-1 py-0.5 text-xs text-primary-800">
            {token.slice(1, -1)}
          </code>
        )
      }
      const match = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
      if (match) {
        return (
          <a
            key={`link-${idx}`}
            href={match[2]}
            target="_blank"
            rel="noreferrer"
            className="text-primary-700 underline decoration-primary-300 underline-offset-2"
          >
            {match[1]}
          </a>
        )
      }
      return <span key={`text-${idx}`}>{token}</span>
    })
}

function renderMarkdown(content: string): ReactNode[] {
  const lines = content.split('\n')
  const blocks: ReactNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    if (line.trim() === '') {
      index += 1
      continue
    }

    if (line.startsWith('```')) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length && lines[index].startsWith('```')) {
        index += 1
      }
      blocks.push(
        <pre
          key={`code-block-${blocks.length}`}
          className="overflow-x-auto rounded-xl border border-primary-100 bg-primary-900 p-3 text-xs text-primary-100"
        >
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      const level = heading[1].length
      const title = heading[2].trim()
      const className =
        level === 1
          ? 'text-lg font-semibold text-primary-900'
          : level === 2
            ? 'text-base font-semibold text-primary-800'
            : 'text-sm font-semibold text-primary-800'
      blocks.push(
        <h3 key={`heading-${blocks.length}`} className={className}>
          {title}
        </h3>,
      )
      index += 1
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, '').trim())
        index += 1
      }
      blocks.push(
        <ul key={`list-${blocks.length}`} className="list-disc space-y-1 pl-5 text-sm text-primary-800">
          {items.map((item, idx) => (
            <li key={`li-${idx}`}>{renderInline(item)}</li>
          ))}
        </ul>,
      )
      continue
    }

    const paragraph: string[] = [line]
    index += 1
    while (
      index < lines.length &&
      lines[index].trim() !== '' &&
      !lines[index].startsWith('```') &&
      !/^(#{1,3})\s+/.test(lines[index]) &&
      !/^\s*[-*]\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index])
      index += 1
    }
    blocks.push(
      <p key={`p-${blocks.length}`} className="whitespace-pre-wrap text-sm leading-6 text-primary-800">
        {renderInline(paragraph.join('\n'))}
      </p>,
    )
  }

  return blocks
}

export default function CitationViewer({ open, loading, error, data, onClose }: Props) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 bg-primary-950/30 p-3 backdrop-blur-sm md:p-8">
      <div className="mx-auto flex h-full max-w-4xl flex-col rounded-2xl border border-primary-200 bg-white shadow-soft">
        <div className="flex items-center justify-between border-b border-primary-100 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-primary-900">{data?.title || '参考来源'}</p>
            <p className="truncate text-xs text-primary-600">{data?.url || '-'}</p>
          </div>
          <div className="flex items-center gap-2">
            {(data?.external_url || data?.url) && (
              <a
                href={data?.external_url || data?.url || '#'}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-primary-200 px-2 py-1 text-xs text-primary-700 hover:bg-primary-50"
              >
                打开原文
              </a>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-primary-200 px-2 py-1 text-xs text-primary-700 hover:bg-primary-50"
            >
              关闭
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {loading && <p className="text-sm text-primary-700">正在加载引用内容...</p>}
          {!loading && error && <p className="text-sm text-red-600">{error}</p>}
          {!loading && !error && data && (
            <div className="space-y-3">
              {data.truncated && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  内容较长，仅展示前 120000 字符。
                </div>
              )}
              {data.render_mode === 'markdown' ? (
                <div className="space-y-3">{renderMarkdown(data.content)}</div>
              ) : (
                <pre className="whitespace-pre-wrap text-sm leading-6 text-primary-800">{data.content}</pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
