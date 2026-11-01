const SENTENCE_ENDINGS = new Set(['。', '！', '？', '；', '.', '!', '?', ';', '\n'])

/**
 * 累积流式文本，并只返回已经结束的完整句子。
 * `replace` 用于服务端清理工具调用文本后的 content_clean 事件。
 */
export class TtsSentenceBuffer {
  private buffer = ''

  append(text: string): string[] {
    if (!text)
      return []

    this.buffer += text
    const sentences: string[] = []
    let start = 0

    for (let index = 0; index < this.buffer.length; index++) {
      if (!SENTENCE_ENDINGS.has(this.buffer[index]!))
        continue

      while (index + 1 < this.buffer.length && SENTENCE_ENDINGS.has(this.buffer[index + 1]!))
        index++

      const sentence = this.buffer.slice(start, index + 1).trim()
      if (sentence)
        sentences.push(sentence)
      start = index + 1
    }

    this.buffer = this.buffer.slice(start)
    return sentences
  }

  replace(text: string): void {
    this.buffer = text
  }

  flush(): string | null {
    const text = this.buffer.trim()
    this.buffer = ''
    return text || null
  }

  clear(): void {
    this.buffer = ''
  }
}
