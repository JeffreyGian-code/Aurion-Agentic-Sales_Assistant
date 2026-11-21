import { AnimatePresence, motion } from 'motion/react'
import { ArrowUp, Clock, Square } from 'lucide-react'
import { useLayoutEffect, type RefObject } from 'react'
import { MAX_MESSAGE_LENGTH } from '../api/types'
import { IP_COOLDOWN_SECONDS } from '../hooks/useChat'
import { cn } from '../lib/utils'

interface Props {
  value: string
  onChange: (v: string) => void
  onSend: (text: string) => void
  onStop: () => void
  pending: boolean
  cooldown: number
  budgetExhausted: boolean
  budgetResetsAt: number | null
  inputRef: RefObject<HTMLTextAreaElement | null>
}

export function Composer({ value, onChange, onSend, onStop, pending, cooldown, budgetExhausted, budgetResetsAt, inputRef }: Props) {
  const trimmed = value.trim()
  const length = value.length
  const tooLong = length > MAX_MESSAGE_LENGTH
  const blocked = pending || cooldown > 0 || budgetExhausted
  const canSend = !!trimmed && !tooLong && !blocked

  // Grow in whole lines, including when the available width changes.
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    const resize = () => {
      const style = getComputedStyle(el)
      const lineHeight = parseFloat(style.lineHeight)
      const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
      el.style.height = 'auto'
      const lines = Math.max(1, Math.ceil((el.scrollHeight - padding) / lineHeight))
      el.style.height = `${Math.min(lines, 8) * lineHeight + padding}px`
      el.style.overflowY = lines > 8 ? 'auto' : 'hidden'
    }
    resize()
    let width = el.clientWidth
    const observer = new ResizeObserver(() => {
      if (el.clientWidth !== width) {
        width = el.clientWidth
        resize()
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [value, inputRef])

  const submit = () => {
    if (!canSend) return
    onSend(trimmed)
  }


  return (
    <div className="relative shrink-0 px-3 pb-4 pt-3 sm:px-6 sm:pb-6">
      <div className="relative w-full">
        {budgetExhausted && (
          <p role="status" className="mb-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-100">
            You’ve used all 7 calls.{budgetResetsAt ? ` Your budget renews ${new Date(budgetResetsAt * 1000).toLocaleString()}.` : ''} Resetting the conversation keeps this limit.
          </p>
        )}
        <AnimatePresence>
          {cooldown > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="mb-2 overflow-hidden rounded-xl border border-amber-200 bg-amber-50 text-sm dark:border-amber-500/30 dark:bg-amber-500/10">
                <div className="flex items-center gap-2 px-3 py-2 text-amber-900 dark:text-amber-100">
                  <Clock className="size-4 shrink-0" />
                  <span>
                    Too many requests. You can send again in <b className="tabular-nums">{cooldown}s</b>.
                  </span>
                </div>
                <motion.div
                  className="h-0.5 bg-amber-400"
                  initial={false}
                  animate={{ width: `${(cooldown / IP_COOLDOWN_SECONDS) * 100}%` }}
                  transition={{ ease: 'linear', duration: 1 }}
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div
          className={cn(
            'composer-glass flex items-end gap-2 rounded-[28px] border p-2 transition duration-200',
            tooLong
              ? 'border-red-400 ring-2 ring-red-400/20'
              : 'border-white/80 focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-500/10 dark:border-white/15 dark:focus-within:border-brand-400/60',
          )}
        >
          <textarea
            ref={inputRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                submit()
              }
            }}
            rows={1}
            placeholder="Ask Aurion anything"
            aria-label="Message"
            className="block min-w-0 flex-1 resize-none bg-transparent px-3 py-2 text-base leading-6 text-slate-800 outline-none placeholder:text-slate-500 dark:text-slate-100 dark:placeholder:text-slate-400"
          />

          <div className="flex shrink-0 items-center justify-end">
            {pending ? (
              <motion.button
                whileTap={{ scale: 0.9 }}
                onClick={onStop}
                className="grid size-10 shrink-0 place-items-center rounded-full bg-slate-900 text-white transition hover:bg-slate-700 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
                aria-label="Stop waiting for reply"
                title="Stop"
              >
                <Square className="size-3.5 fill-current" />
              </motion.button>
            ) : (
              <motion.button
                whileTap={canSend ? { scale: 0.9 } : undefined}
                onClick={submit}
                disabled={!canSend}
                className={cn(
                  'grid size-10 shrink-0 place-items-center rounded-full transition',
                  canSend
                    ? 'bg-brand-600 text-white shadow-md shadow-brand-600/20 hover:bg-brand-500'
                    : 'bg-white/50 text-slate-400 dark:bg-white/10 dark:text-slate-500',
                )}
                aria-label="Send message"
              >
                {cooldown > 0 ? <span className="text-[11px] font-semibold tabular-nums">{cooldown}</span> : <ArrowUp className="size-[18px]" />}
              </motion.button>
            )}
          </div>
        </div>

        {tooLong && (
          <p role="alert" className="mt-2 text-center text-[11px] text-red-500">
            Message is too long. Keep it under {MAX_MESSAGE_LENGTH} characters.
          </p>
        )}
      </div>
    </div>
  )
}
