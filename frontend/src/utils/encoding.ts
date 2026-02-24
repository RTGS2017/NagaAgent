export const decoder = new TextDecoder('utf-8')

export interface StreamChunk {
  type: 'content' | 'reasoning' | 'content_clean' | 'round_start' | 'tool_calls' | 'tool_results' | 'round_end' | 'auth_expired' | 'token_refreshed' | 'compress_start' | 'compress_progress' | 'compress_end' | 'compress_info'
  text?: string
  round?: number
  calls?: Array<{ agentType: string, service_name?: string, tool_name?: string, message?: string }>
  results?: Array<{ service_name: string, tool_name?: string, result: string, status: string }>
  has_more?: boolean
}

export function decodeStreamChunk(data: string): StreamChunk {
  try {
    const parsed = JSON.parse(data)
    if (parsed && typeof parsed === 'object' && 'type' in parsed) {
      return parsed as StreamChunk
    }
  }
  catch {
    // Fallback for plain text
  }
  return { type: 'content', text: data }
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
