/**
 * Minimal server-sent-events reader over fetch.
 *
 * `EventSource` cannot send the admin bearer token, so the log stream is read
 * with fetch and parsed here. Each frame from KARR is `data: <line>` with the
 * line's `\`, `\r` and `\n` escaped (K-D2); `event: end` and `event: error`
 * close it.
 */

export interface SseEvent {
  event: string
  data: string
}

/** Pending bytes without a frame terminator are capped so a container that
 * prints without newlines cannot grow the tab without bound. */
export const MAX_PENDING_CHARS = 1024 * 1024
/** A single event's data is truncated past this many characters. */
export const MAX_EVENT_CHARS = 64 * 1024
export const TRUNCATED_MARKER = ' …[truncated]'

/** Undo KARR's frame escaping: `\\n` -> newline, `\\r` -> carriage return, `\\\\` -> backslash. */
export function unescapeLine(data: string): string {
  return data.replace(/\\(n|r|\\)/g, (_match, c: string) =>
    c === 'n' ? '\n' : c === 'r' ? '\r' : '\\',
  )
}

/** Parse one blank-line-terminated block into an event, ignoring comments. */
export function parseBlock(block: string): SseEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line === '' || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  if (data.length === 0 && event === 'message') return null
  let joined = data.join('\n')
  if (joined.length > MAX_EVENT_CHARS) joined = joined.slice(0, MAX_EVENT_CHARS) + TRUNCATED_MARKER
  return { event, data: joined }
}

/** Normalise `\r\n` and lone `\r` terminators to `\n`, holding back a trailing `\r`
 * that may be the first half of a pair split across chunks. */
function normalise(buffer: string): { ready: string; held: string } {
  const held = buffer.endsWith('\r') ? '\r' : ''
  const ready = buffer.slice(0, buffer.length - held.length).replace(/\r\n|\r/g, '\n')
  return { ready, held }
}

/** Yield events from a streaming body until it closes or the signal aborts. */
export async function* readEvents(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (!signal?.aborted) {
      const { value, done } = await reader.read()
      if (done) break
      const { ready, held } = normalise(buffer + decoder.decode(value, { stream: true }))
      buffer = ready
      let split = buffer.indexOf('\n\n')
      while (split !== -1) {
        const parsed = parseBlock(buffer.slice(0, split))
        buffer = buffer.slice(split + 2)
        if (parsed) yield parsed
        split = buffer.indexOf('\n\n')
      }
      if (buffer.length > MAX_PENDING_CHARS) {
        // no terminator in sight: emit what we have, truncated, and drop the rest
        const parsed = parseBlock(buffer.slice(0, MAX_EVENT_CHARS))
        buffer = ''
        if (parsed) yield { ...parsed, data: parsed.data + TRUNCATED_MARKER }
      }
      buffer += held
    }
    const tail = parseBlock(normalise(buffer).ready)
    if (tail) yield tail
  } finally {
    reader.releaseLock()
    await body.cancel().catch(() => undefined)
  }
}
