/**
 * Minimal server-sent-events reader over fetch.
 *
 * `EventSource` cannot send the admin bearer token, so the log stream is read
 * with fetch and parsed here. Each frame from KARR is `data: <line>` with the
 * line's `\r` and `\n` escaped (K-D2); `event: end` and `event: error` close it.
 */

export interface SseEvent {
  event: string
  data: string
}

/** Undo KARR's frame escaping: `\\n` -> newline, `\\r` -> carriage return. */
export function unescapeLine(data: string): string {
  return data.replace(/\\(n|r|\\)/g, (_match, c: string) =>
    c === 'n' ? '\n' : c === 'r' ? '\r' : '\\',
  )
}

/** Parse one blank-line-terminated block into an event, ignoring comments. */
export function parseBlock(block: string): SseEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const raw of block.split('\n')) {
    const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw
    if (line === '' || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  if (data.length === 0 && event === 'message') return null
  return { event, data: data.join('\n') }
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
      buffer += decoder.decode(value, { stream: true })
      let split = buffer.indexOf('\n\n')
      while (split !== -1) {
        const parsed = parseBlock(buffer.slice(0, split))
        buffer = buffer.slice(split + 2)
        if (parsed) yield parsed
        split = buffer.indexOf('\n\n')
      }
    }
    const tail = parseBlock(buffer)
    if (tail) yield tail
  } finally {
    reader.releaseLock()
    await body.cancel().catch(() => undefined)
  }
}
