import { describe, expect, it } from 'vitest'
import { MAX_EVENT_CHARS, MAX_PENDING_CHARS, TRUNCATED_MARKER, parseBlock, readEvents, unescapeLine } from './sse'

function stream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

describe('unescapeLine', () => {
  it('reverses the relay escaping (K-D2)', () => {
    expect(unescapeLine('a\\nb\\rc')).toBe('a\nb\rc')
    // the relay escapes the backslash first, so an escaped backslash + n is a literal \n
    expect(unescapeLine('C:\\\\new\\\\rows')).toBe('C:\\new\\rows')
    expect(unescapeLine('a\\\\\\nb')).toBe('a\\\nb')
    expect(unescapeLine('plain')).toBe('plain')
  })
})

describe('parseBlock', () => {
  it('reads data, event and ignores comments', () => {
    expect(parseBlock('data: hello')).toEqual({ event: 'message', data: 'hello' })
    expect(parseBlock('event: end\ndata: ')).toEqual({ event: 'end', data: '' })
    expect(parseBlock(': keepalive')).toBeNull()
    expect(parseBlock('data: one\ndata: two')).toEqual({ event: 'message', data: 'one\ntwo' })
  })
})

describe('readEvents', () => {
  it('reassembles frames split across chunks', async () => {
    const events = []
    for await (const ev of readEvents(stream(['data: fir', 'st\n\n: keepalive\n\ndata: second\n\nevent: end\ndata: \n\n']))) {
      events.push(ev)
    }
    expect(events).toEqual([
      { event: 'message', data: 'first' },
      { event: 'message', data: 'second' },
      { event: 'end', data: '' },
    ])
  })

  it('accepts CRLF terminators split across chunks', async () => {
    const events = []
    for await (const ev of readEvents(stream(['data: one\r', '\n\r\ndata: two\r\n\r\n']))) events.push(ev)
    expect(events).toEqual([
      { event: 'message', data: 'one' },
      { event: 'message', data: 'two' },
    ])
  })

  it('caps a line without a terminator instead of buffering it forever', async () => {
    const huge = 'x'.repeat(MAX_PENDING_CHARS + 10)
    const events = []
    for await (const ev of readEvents(stream(['data: ' + huge]))) events.push(ev)
    expect(events).toHaveLength(1)
    expect(events[0]?.data.length).toBeLessThanOrEqual(MAX_EVENT_CHARS + TRUNCATED_MARKER.length)
    expect(events[0]?.data.endsWith(TRUNCATED_MARKER)).toBe(true)
  })

  it('truncates one oversized event', () => {
    const parsed = parseBlock('data: ' + 'y'.repeat(MAX_EVENT_CHARS + 5))
    expect(parsed?.data).toHaveLength(MAX_EVENT_CHARS + TRUNCATED_MARKER.length)
  })
})
