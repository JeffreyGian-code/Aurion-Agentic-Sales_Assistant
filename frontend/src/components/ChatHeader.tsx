import { Menu, Monitor, Moon, RefreshCw, RotateCcw, StickyNote, Sun } from 'lucide-react'
import { USE_MOCK } from '../api/client'
import type { HealthStatus } from '../hooks/useHealth'
import type { Theme } from '../hooks/useTheme'
import type { Conversation } from '../lib/types'
import { cn } from '../lib/utils'

interface Props {
  conversation: Conversation | null
  health: HealthStatus
  onRefreshHealth: () => void
  theme: Theme
  onCycleTheme: () => void
  onOpenSidebar: () => void
  onReset: () => void
  onToggleNote: () => void
  noteOpen: boolean
  pending: boolean
  calls: number
  callLimit: number
}

export function ChatHeader({ conversation, health, onRefreshHealth, theme, onCycleTheme, onOpenSidebar, onReset, onToggleNote, noteOpen, pending, calls, callLimit }: Props) {
  const ThemeIcon = theme === 'light' ? Sun : theme === 'dark' ? Moon : Monitor

  return (
    <header className="app-header relative z-10 flex min-h-20 shrink-0 flex-wrap items-center gap-2 px-4 py-4 sm:px-6">
      <button
        onClick={onOpenSidebar}
        className="material-control rounded-full p-2 md:hidden"
        aria-label="Open execution dashboard"
      >
        <Menu className="size-5" />
      </button>

      <div className="min-w-28 flex-1">
        <h1 className="aurion-wordmark truncate text-xl font-medium tracking-tight sm:text-2xl" title={conversation?.title}>Aurion</h1>
        <p className="text-[11px] text-slate-500" aria-live="polite">{calls}/{callLimit} calls used · Renews every 24 hours</p>
      </div>

      <button type="button" onClick={onReset} disabled={pending} title="Clear conversation context. Your call count and limits stay the same."
        className="material-control flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-medium disabled:opacity-40">
        <RotateCcw className="size-3.5" /> Reset conversation
      </button>
      <button type="button" onClick={onToggleNote} aria-expanded={noteOpen} aria-controls="developer-note"
        className="material-control flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-medium">
        <StickyNote className="size-3.5" /> Note
      </button>

      {USE_MOCK && (
        <span className="hidden rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800 sm:inline dark:bg-amber-500/15 dark:text-amber-300">
          MOCK API
        </span>
      )}

      <button
        onClick={onRefreshHealth}
        disabled={health === 'checking'}
        className="material-control group flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-medium"
        title="Check API, database and AI provider status"
      >
        <span className="relative flex size-2">
          {health === 'online' && (
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />
          )}
          <span
            className={cn(
              'relative inline-flex size-2 rounded-full',
              health === 'online' && 'bg-emerald-500',
              health === 'offline' && 'bg-red-500',
              (health === 'checking' || health === 'degraded') && 'bg-amber-400',
              health === 'unchecked' && 'bg-slate-400',
            )}
          />
        </span>
        <span className="hidden sm:inline">
          {health === 'online' ? 'Checks passed' : health === 'offline' ? 'Check failed' : health === 'degraded' ? 'Service issue' : health === 'checking' ? 'Checking' : 'Check services'}
        </span>
        <RefreshCw className={cn('size-3 text-slate-400 transition group-hover:rotate-180', health === 'checking' && 'animate-spin')} />
      </button>

      <button
        onClick={onCycleTheme}
        className="material-control rounded-full p-2.5"
        aria-label={`Theme: ${theme}. Click to change`}
        title={`Theme: ${theme}`}
      >
        <ThemeIcon className="size-[18px]" />
      </button>
    </header>
  )
}
