<script setup lang="ts">
withDefaults(defineProps<{
  name: string
  description?: string
  layout?: 'row' | 'column'
}>(), {
  layout: 'row',
})
</script>

<template>
  <label :class="layout === 'row' ? 'grid grid-cols-2' : 'flex flex-col'">
    <div class="flex flex-col justify-center gap-1">
      <div class="font-bold">{{ name }}</div>
      <div v-if="description" class="text-sm text-gray-500">{{ description }}</div>
    </div>
    <div class="flex flex-col justify-center">
      <slot />
    </div>
  </label>
</template>
