import { mockHealth, mockSendMessage } from './mock'
import { ChatError, type ApiError, type ChatDelta, type ChatProgress, type ChatResponse } from './types'

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api').replace(/\/$/, '')
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

const REQUEST_TIMEOUT_MS = 60_000

function detailToText(detail: ApiError['detail'] | undefined, fallback: string): string {
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return fallback
  return detail.filter(d => d && typeof d.msg === "string").map((d) => d.msg).join('; ') || fallback
}

function toChatError(status: number, detail: ApiError['detail'] | undefined, code?: string | null, retryAfter?: number): ChatError {
  const text = detailToText(detail, 'Something went wrong while processing your request.')
  if (code === 'session-expired') return new ChatError('session-expired', text, status)
  if (code === 'session-limit') return new ChatError('session-limit', text, status, retryAfter)
  if (status === 504) return new ChatError('timeout', text, status)
  if (code === 'conversation-limit') return new ChatError('conversation-limit', text, status)
  if (status === 422) return new ChatError('validation', text, status)
  if (status === 429) {
    return new ChatError('ip-rate-limit', text, status, retryAfter)
  }
  return new ChatError('server', text, status)
}

/**
 * POST /api/chat/stream. Throws ChatError for every failure except a caller-initiated abort,
 * which rethrows the original AbortError.
 */
export async function sendMessage(
  message: string,
  sessionId?: string | null,
  externalSignal?: AbortSignal,
  onProgress?: (progress: ChatProgress) => void,
  onStarted?: (sessionId: string) => void,
  onDelta?: (delta: ChatDelta) => void,
  resetContext = false,
  requestId?: string,
): Promise<ChatResponse> {
  if (USE_MOCK) {
    onProgress?.({ phase: 'processing', label: 'Waiting for simulated response…' })
    const id = sessionId ?? crypto.randomUUID()
    onStarted?.(id)
    const response = await mockSendMessage(message, id, externalSignal)
    onProgress?.({ phase: 'writing', label: 'Writing simulated response?' })
    return response
  }

  const controller = new AbortController()
  let timedOut = false
  let timeout: ReturnType<typeof setTimeout> | undefined
  const resetTimeout = () => {
    clearTimeout(timeout)
    timeout = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, REQUEST_TIMEOUT_MS)
  }
  resetTimeout()
  const deadline = setTimeout(() => { timedOut = true; controller.abort() }, 120_000)
  const onExternalAbort = () => controller.abort()
  externalSignal?.addEventListener('abort', onExternalAbort)
  if (externalSignal?.aborted) controller.abort()

  try {
    let res: Response
    try {
      res = await fetch(`${API_URL}/chat/stream`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message.trim(), session_id: sessionId ?? null, reset_context: resetContext, request_id: requestId }),
        signal: controller.signal,
      })
    } catch (err) {
      if (externalSignal?.aborted) throw err
      if (timedOut) {
        throw new ChatError('timeout', 'The assistant took too long to respond. Please try again.')
      }
      throw new ChatError('network', "Can't reach the server. Check that the API is running.")
    }

    if (!res.ok) {
      const body: Partial<ApiError> = await res.json().catch(() => ({ detail: res.statusText }))
      throw toChatError(res.status, body?.detail, res.headers.get("X-Error-Code"), Number(res.headers.get("Retry-After")) || undefined)
    }

    if (!res.body) throw new ChatError('server', 'The server did not return a response stream.')
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        resetTimeout() // Heartbeats keep slow, healthy model calls alive.
        buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n')
        let boundary: number
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          const lines = frame.split('\n')
          const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
          const data = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
          if (!data) continue // SSE heartbeat comment.
          const invalid = () => new ChatError('server', 'The server returned an invalid response.')
          let payload
          try { payload = JSON.parse(data) } catch { throw invalid() }
          if (!payload || typeof payload !== 'object') throw invalid()
          if ((event === 'started' || event === 'completed') && (typeof payload.session_id !== 'string' || !payload.session_id)) throw invalid()
          if (sessionId && (event === 'started' || event === 'completed') && payload.session_id !== sessionId) throw invalid()
          if (event === 'completed' && (typeof payload.reply !== 'string' || !payload.reply.trim())) throw invalid()
          if (event === 'progress' && (!['processing','writing','tool_started','tool_finished','tool_failed'].includes(payload.phase) || typeof payload.label !== 'string' ||
              ['tool','run_id'].some(key => payload[key] != null && typeof payload[key] !== 'string') ||
              (payload.duration_ms != null && !Number.isFinite(payload.duration_ms)))) throw invalid()
          if (event === 'delta' && (typeof payload.text !== 'string' || (payload.reset !== undefined && typeof payload.reset !== 'boolean'))) throw invalid()
          if (event === 'error' && (!Number.isInteger(payload.status) || typeof payload.detail !== 'string')) throw invalid()
          if (event === 'started') onStarted?.(payload.session_id)
          if (event === 'progress') onProgress?.(payload as ChatProgress)
          if (event === 'delta') onDelta?.(payload as ChatDelta)
          if (event === 'error') throw toChatError(payload.status, payload.detail, payload.code)
          if (event === 'completed') return payload as ChatResponse
        }
      }
      throw new ChatError('network', 'The connection closed before the assistant finished. Please try again.')
    } finally {
      await reader.cancel().catch(() => {})
      reader.releaseLock()
    }
  } catch (err) {
    if (externalSignal?.aborted) throw err
    if (timedOut) throw new ChatError('timeout', 'The connection stopped responding. Please try again.')
    if (err instanceof ChatError) throw err
    throw new ChatError('network', 'The response connection was interrupted. Please try again.')
  } finally {
    clearTimeout(timeout)
    clearTimeout(deadline)
    externalSignal?.removeEventListener('abort', onExternalAbort)
  }
}

export interface ServiceCheck {
  status: 'ok' | 'unavailable' | 'unknown'
  detail: string
}

export interface ChatUsage {
  calls: number
  limit: number
  resets_at: number | null
}

export function validUsage(value: unknown): value is ChatUsage {
  if (!value || typeof value !== 'object') return false
  const u = value as ChatUsage
  return Number.isInteger(u.calls) && Number.isInteger(u.limit) && u.limit > 0 && u.calls >= 0 && u.calls <= u.limit &&
    (u.calls === 0 ? u.resets_at === null : Number.isFinite(u.resets_at))
}

export async function getChatUsage(sessionId: string): Promise<ChatUsage> {
  const res = await fetch(`${API_URL}/chat/usage/${encodeURIComponent(sessionId)}`, { credentials: "include", signal: AbortSignal.timeout(12_000) })
  if (!res.ok) throw toChatError(res.status, 'Could not check usage', res.headers.get('X-Error-Code'))
  const value = await res.json()
  if (!validUsage(value)) throw new Error("Invalid usage response")
  return value
}

export interface ServiceHealth {
  api: ServiceCheck
  database: ServiceCheck
  ai: ServiceCheck
}

/** Manual connectivity checks; never invokes the chat model. */
export async function checkHealth(): Promise<ServiceHealth> {
  if (USE_MOCK) {
    await mockHealth()
    const mocked: ServiceCheck = { status: 'ok', detail: 'Simulated result (mock mode).' }
    return { api: mocked, database: mocked, ai: mocked }
  }
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 12_000)
  try {
    const res = await fetch(`${API_URL}/health/services`, { signal: controller.signal })
    if (!res.ok) throw new Error(`Status check returned HTTP ${res.status}`)
    const body = await res.json() as ServiceHealth
    for (const name of ['api', 'database', 'ai'] as const) {
      if (!body[name] || !['ok', 'unavailable', 'unknown'].includes(body[name].status) || typeof body[name].detail !== 'string') {
        throw new Error('Invalid status response')
      }
    }
    return body
  } finally {
    clearTimeout(timeout)
  }
}
