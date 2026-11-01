import assert from 'node:assert/strict'
import test from 'node:test'
import { TtsSentenceBuffer } from '../src/utils/ttsText.ts'

test('流式文本按完整句子输出并保留尾部', () => {
  const buffer = new TtsSentenceBuffer()

  assert.deepEqual(buffer.append('你好。今天'), ['你好。'])
  assert.deepEqual(buffer.append('过得怎么样？还不错'), ['今天过得怎么样？'])
  assert.equal(buffer.flush(), '还不错')
})

test('content_clean 可以替换尚未播放的工具调用原文', () => {
  const buffer = new TtsSentenceBuffer()

  buffer.append('让我查一下```tool\n{"agentType":"live2d"}')
  buffer.replace('让我查一下')

  assert.equal(buffer.flush(), '让我查一下')
  assert.equal(buffer.flush(), null)
})

test('连续结束符作为同一句处理', () => {
  const buffer = new TtsSentenceBuffer()

  assert.deepEqual(buffer.append('真的吗？！下一句。'), ['真的吗？！', '下一句。'])
})
