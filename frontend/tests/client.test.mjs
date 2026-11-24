import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'

// Run the real TypeScript client with Node's test runner, without a browser or API.
const asModule = (source) => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const compile = (path) => ts.transpileModule(readFileSync(new URL(path, import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const types = asModule(compile('../src/api/types.ts'))
const mock = asModule('export const mockHealth = () => {}; export const mockSendMessage = () => {};')
const client = compile('../src/api/client.ts')
  .replaceAll("'./types'", JSON.stringify(types))
  .replaceAll("'./mock'", JSON.stringify(mock))
  .replaceAll('import.meta.env', '({})')
const { sendMessage, getChatUsage } = await import(asModule(client))
const frame = (event, payload) => `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`

test('reset keeps the session identity and requests fresh context', async (t) => {
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    assert.deepEqual(JSON.parse(options.body), { message: 'Hello', session_id: 'same-session', reset_context: true })
    return stream(frame('completed', { session_id: 'same-session', reply: 'Fresh start' }))
  })
  await sendMessage('Hello', 'same-session', undefined, undefined, undefined, undefined, true)
})

function stream(text) {
  const bytes = new TextEncoder().encode(text)
  return new Response(new ReadableStream({
    start(controller) {
      // Split inside every JSON field, event boundary, and UTF-8 character.
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte))
      controller.close()
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
}

test('reads fragmented SSE, heartbeats, tool events, Unicode, and final reply', async (t) => {
  const progress = []
  const sessions = []
  t.mock.method(globalThis, 'fetch', async (url) => {
    assert.match(url, /\/chat\/stream$/)
    return stream(frame('started', { session_id: 'abc' }) + ': heartbeat\n\n' +
      frame('progress', { phase: 'tool_started', tool: 'calculate_emi', run_id: '1', label: 'Calculating EMI…', input: { principal: 100000 } }) +
      frame('progress', { phase: 'tool_finished', tool: 'calculate_emi', run_id: '1', label: 'Processing results…', output: { emi: 2500 } }) +
      frame('completed', { session_id: 'abc', reply: 'EMI ₹2,500' }))
  })
  const result = await sendMessage('EMI?', null, undefined, (p) => progress.push(p), (id) => sessions.push(id))
  assert.deepEqual(result, { session_id: 'abc', reply: 'EMI ₹2,500' })
  assert.deepEqual(sessions, ['abc'])
  assert.deepEqual(progress.map((p) => p.phase), ['tool_started', 'tool_finished'])
  assert.equal(progress[0].label, 'Calculating EMI…')
  assert.deepEqual(progress[0].input, { principal: 100000 })
  assert.deepEqual(progress[1].output, { emi: 2500 })
})

test('maps streamed conversation-limit errors and HTTP rate limits', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => stream(frame('error', {
    status: 429, code: 'conversation-limit', detail: 'Please start a new conversation.',
  })))
  await assert.rejects(sendMessage('Hi'), (error) => error.kind === 'conversation-limit')
  fetch.mock.mockImplementation(async () => new Response(JSON.stringify({ detail: 'Too many requests.' }), { status: 429 }))
  await assert.rejects(sendMessage('Hi'), (error) => error.kind === 'ip-rate-limit')
})

test('delivers text deltas before completion and supports answer resets', async (t) => {
  let output
  const deltas = []
  t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({
    start(controller) { output = controller },
  })))
  let gotDelta
  const firstDelta = new Promise((resolve) => { gotDelta = resolve })
  let completed = false
  const result = sendMessage('Hi', null, undefined, undefined, undefined, (delta) => {
    deltas.push(delta)
    gotDelta()
  }).then((response) => { completed = true; return response })
  const write = (event, data) => output.enqueue(new TextEncoder().encode(frame(event, data)))
  write('delta', { text: 'Searching…' })
  await firstDelta
  assert.equal(completed, false)
  write('delta', { text: '', reset: true })
  write('delta', { text: 'Hello ₹' })
  write('delta', { text: ' world' })
  write('completed', { session_id: 'abc', reply: 'Hello ₹ world' })
  assert.equal((await result).reply, 'Hello ₹ world')
  assert.deepEqual(deltas, [
    { text: 'Searching…' }, { text: '', reset: true }, { text: 'Hello ₹' }, { text: ' world' },
  ])
})

test('rejects an interrupted stream instead of treating it as a completed reply', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => stream(frame('started', { session_id: 'abc' })))
  await assert.rejects(sendMessage('Hi'), (error) => error.kind === 'network')
})

test('accepts CRLF event boundaries split across network chunks', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => stream(frame('completed', {
    session_id: 'abc', reply: 'Hello',
  }).replaceAll('\n', '\r\n')))
  assert.equal((await sendMessage('Hi')).reply, 'Hello')
})

test('caller cancellation aborts the streaming request', async (t) => {
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async (_url, { signal }) => new Response(new ReadableStream({
    start(streamController) {
      signal.addEventListener('abort', () => streamController.error(new DOMException('Aborted', 'AbortError')))
      controller.abort()
    },
  })))
  await assert.rejects(sendMessage('Hi', null, controller.signal), (error) => error.name === 'AbortError')
})


test('classifies server quota codes and rejects malformed completion data', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response(
    JSON.stringify({ detail: 'Budget used' }), { status: 429, headers: { 'X-Error-Code': 'session-limit', 'Retry-After': '7200' } },
  ))
  await assert.rejects(sendMessage('Hi'), e => e.kind === 'session-limit' && e.retryAfter === 7200)
  fetch.mock.mockImplementation(async () => stream(frame('completed', { reply: {} })))
  await assert.rejects(sendMessage('Hi'), e => e.kind === 'server')
})

for (const withHeader of [true, false]) {
  test(`recovers a stale session once (error header: ${withHeader})`, async (t) => {
    const requests = []
    const sessions = []
    t.mock.method(globalThis, 'fetch', async (_url, options) => {
      assert.equal(options.credentials, 'include')
      requests.push(JSON.parse(options.body))
      return requests.length === 1
        ? new Response(JSON.stringify({ detail: 'This conversation has expired.' }), {
          status: 404, headers: withHeader ? { 'X-Error-Code': 'session-expired' } : {},
        })
        : stream(frame('started', { session_id: 'recovered' }) +
          frame('completed', { session_id: 'recovered', reply: 'Hello' }))
    })
    const result = await sendMessage('Hello', 'stale', undefined, undefined, id => sessions.push(id), undefined, true, 'turn-1')
    assert.equal(result.reply, 'Hello')
    assert.deepEqual(sessions, ['recovered'])
    assert.deepEqual(requests, [
      { message: 'Hello', session_id: 'stale', reset_context: true, request_id: 'turn-1' },
      { message: 'Hello', session_id: null, reset_context: true, request_id: 'turn-1' },
    ])
  })
}

test('stops recovery after one retry and classifies headerless usage expiry', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response(
    JSON.stringify({ detail: 'This conversation has expired.' }), { status: 404 },
  ))
  await assert.rejects(sendMessage('Hello', 'stale'), e => e.kind === 'session-expired')
  assert.equal(fetch.mock.callCount(), 2)
  await assert.rejects(getChatUsage('stale'), e => e.kind === 'session-expired')
})

test('does not retry unrelated 404s or errors after generation starts', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response(
    JSON.stringify({ detail: 'Not Found' }), { status: 404 },
  ))
  await assert.rejects(sendMessage('Hello', 'current'), e => e.kind === 'server')
  assert.equal(fetch.mock.callCount(), 1)
  fetch.mock.mockImplementation(async () => stream(frame('started', { session_id: 'current' }) +
    frame('error', { status: 404, code: 'session-expired', detail: 'This conversation has expired.' })))
  await assert.rejects(sendMessage('Hello', 'current'), e => e.kind === 'session-expired')
  assert.equal(fetch.mock.callCount(), 2)
})
