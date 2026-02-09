<script  lang="ts">
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt()

export function render(content: string) {
  return md.render(content)
}
</script>

<script setup lang="ts">
defineProps<{ source: string }>()
</script>

<template>
  <div v-html="render(source)" />
</template>
