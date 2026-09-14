import { describe, expect, it } from 'vitest'
import { parseBlock, readEvents, unescapeLine } from './sse'

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
    expect(unescapeLine('literal \\\\n stays')).toBe('literal \\n stays')
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
})
