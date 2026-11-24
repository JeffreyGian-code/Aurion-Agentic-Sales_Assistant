import { AnimatePresence, motion } from 'motion/react'
import { ArrowDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { PendingRequest } from '../hooks/useChat'
import type { Conversation } from '../lib/types'
import { formatDay } from '../lib/utils'
import { Avatar, Markdown, MessageBubble } from './MessageBubble'
import { TypingIndicator } from './TypingIndicator'

interface Props {
  conversation: Conversation
  pending: PendingRequest | null
  cooldown: number
  budgetExhausted: boolean
  onRetry: (id: string) => void
}

export function MessageList({ conversation, pending, cooldown, budgetExhausted, onRetry }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [atBottom, setAtBottom] = useState(true)
  const isPendingHere = pending?.conversationId === conversation.id
  const messages = conversation.messages

  // Keep pinned to the bottom when new content arrives, unless the user scrolled up.
  useEffect(() => {
    const el = scrollRef.current
    if (el && atBottom) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages.length, isPendingHere, pending?.reply, atBottom])

  // Jump to bottom when switching conversations.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [conversation.id])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80)
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} onScroll={onScroll} className="h-full overflow-y-auto">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-4 py-8 sm:px-8" aria-live="polite">
          {messages.map((m, i) => {
            const prev = messages[i - 1]
            const showDay = !prev || formatDay(prev.createdAt) !== formatDay(m.createdAt)
            return (
              <div key={m.id} className="flex flex-col gap-5">
                {showDay && (
                  <div className="flex items-center gap-3 text-[11px] font-medium tracking-wider text-slate-400 uppercase">
                    <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
                    {formatDay(m.createdAt)}
                    <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
                  </div>
                )}
                <MessageBubble
                  message={m}
                  onRetry={onRetry}
                  canRetry={!pending && (!budgetExhausted || (!!m.requestId && m.errorKind !== "session-limit")) && i === messages.length - 1}
                  cooldown={cooldown}
                />
              </div>
            )
          })}

          <AnimatePresence>
            {isPendingHere && pending && (pending.reply ? (
              <div key="streaming" className="flex gap-3" aria-busy="true">
                <Avatar pulse />
                <div className="min-w-0 flex-1">
                  <div className="inline-block max-w-full px-1 py-2 break-words">
                    <Markdown text={pending.reply} />
                  </div>
                  <p className="mt-1 text-xs text-slate-400" role="status">{pending.status}</p>
                </div>
              </div>
            ) : <TypingIndicator key="typing" startedAt={pending.startedAt} status={pending.status} />)}
          </AnimatePresence>

        </div>
      </div>

      <AnimatePresence>
        {!atBottom && (
          <motion.button
            initial={{ opacity: 0, y: 10, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.9 }}
            onClick={() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })}
            className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-medium shadow-lg backdrop-blur transition hover:bg-white dark:border-slate-700 dark:bg-slate-800/90"
          >
            <ArrowDown className="size-3.5" /> Jump to latest
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  )
}
