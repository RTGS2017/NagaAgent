<script setup lang="ts">
import { AccordionContent, AccordionHeader, AccordionPanel } from 'primevue'

defineProps<{
  value: string
  header?: string
  recoverDefault?: () => void
}>()
</script>

<template>
  <AccordionPanel :value="value">
    <AccordionHeader>
      <div class="w-full flex justify-between items-center pr-4">
        <slot name="header">{{ header }}</slot>
      </div>
    </AccordionHeader>
    <AccordionContent>
      <slot />
    </AccordionContent>
  </AccordionPanel>
</template>
