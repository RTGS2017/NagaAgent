<script setup lang="ts">
import type { ForumComment } from '../types'
import { ref, watch } from 'vue'
import { likeComment } from '../api'

const props = defineProps<{
  comment: ForumComment
  isPostOwner?: boolean
}>()

defineEmits<{
  previewImage: [src: string]
}>()

const liking = ref(false)
const likesCount = ref(props.comment.likesCount)
const liked = ref(props.comment.liked)

watch(
  () => [props.comment.likesCount, props.comment.liked] as const,
  ([nextLikesCount, nextLiked]) => {
    likesCount.value = nextLikesCount
    liked.value = nextLiked
  },
)

function formatTime(iso: string): string {
  const d = new Date(iso)
  const month = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${month}/${day} ${h}:${m}`
}

async function toggleLike() {
  if (liking.value)
    return

  liking.value = true
  try {
    const res = await likeComment(props.comment.id)
    likesCount.value = res.likes
    liked.value = res.liked
  }
  finally {
    liking.value = false
  }
}
</script>

<template>
  <div class="comment-item">
    <div class="flex gap-2">
      <!-- Avatar -->
      <div class="avatar w-7 h-7 rounded-full flex items-center justify-center text-xs shrink-0">
        {{ comment.author.name.charAt(0) }}
      </div>

      <div class="flex-1 min-w-0">
        <!-- Author line -->
        <div class="flex items-center gap-2 text-xs">
          <span class="text-white/70 font-bold">{{ comment.author.name }}</span>
          <span v-if="comment.author.level" class="text-white/25">Lv.{{ comment.author.level }}</span>
          <span v-if="comment.replyToId" class="text-white/30">
            回复了评论
          </span>
          <span class="text-white/20 ml-auto shrink-0">{{ formatTime(comment.createdAt) }}</span>
        </div>

        <!-- Content -->
        <div class="text-white/60 text-xs leading-relaxed mt-1">
          {{ comment.content }}
        </div>

        <!-- Images -->
        <div v-if="comment.images?.length" class="flex gap-2 mt-2 flex-wrap">
          <img
            v-for="(img, i) in comment.images"
            :key="i"
            :src="img"
            class="w-16 h-16 rounded object-cover cursor-pointer hover:brightness-110 transition"
            @click="$emit('previewImage', img)"
          >
        </div>

        <!-- Actions row -->
        <div class="flex items-center gap-3 mt-1.5 text-xs">
          <button
            class="like-btn flex items-center gap-1 border-none bg-transparent cursor-pointer p-0 transition"
            :class="liked ? 'liked' : ''"
            :disabled="liking"
            @click="toggleLike"
          >
            <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
            {{ likesCount }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.comment-item {
  padding: 8px 0;
}

.avatar {
  background: rgba(212, 175, 55, 0.15);
  color: #d4af37;
  border: 1px solid rgba(212, 175, 55, 0.3);
}

.like-btn {
  color: rgba(255, 255, 255, 0.3);
}
.like-btn:hover {
  color: rgba(255, 255, 255, 0.6);
}
.like-btn.liked {
  color: #d4af37;
}
.like-btn.liked svg {
  fill: #d4af37;
}
</style>
