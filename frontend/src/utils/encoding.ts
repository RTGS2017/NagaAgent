export const decoder = new TextDecoder('utf-8')

export interface StreamChunk {
  type: 'content' | 'reasoning'
  text: string
}

export function decodeBase64(base64: string) {
  const binaryString = atob(base64)
  const bytes = new Uint8Array(binaryString.length)

  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i)
  }

  return decoder.decode(bytes)
}

export function decodeStreamChunk(base64: string): StreamChunk {
  const decoded = decodeBase64(base64)
  try {
    const parsed = JSON.parse(decoded)
    if (parsed && typeof parsed === 'object' && 'type' in parsed && 'text' in parsed) {
      return parsed as StreamChunk
    }
  } catch {
    // Fallback for old format (plain text)
  }
  return { type: 'content', text: decoded }
}

export async function* readerToEventStream(reader: ReadableStreamDefaultReader<Uint8Array>): AsyncGenerator<string, void, void> {
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        if (buffer) {
          const events = buffer.split('\n\n')
          for (const event of events.filter(e => e.trim() !== '')) {
            yield event
          }
        }
        return
      }

      buffer += decoder.decode(value, { stream: !done })

      const events = buffer.split('\n\n')
      buffer = events.pop() || ''

      for (const event of events) {
        if (event.trim()) {
          yield event
        }
      }
    }
  }
  finally {
    reader.releaseLock()
  }
}

export async function* eventStreamToMessageStream(events: AsyncGenerator<string>): AsyncGenerator<string, void, void> {
  for await (const event of events) {
    if (event.startsWith('data: ')) {
      const data = event.slice(6)
      if (data === '[DONE]') {
        return
      }
      yield data
    }
  }
}

export function readerToMessageStream(reader: ReadableStreamDefaultReader<Uint8Array>) {
  return eventStreamToMessageStream(readerToEventStream(reader))
}
