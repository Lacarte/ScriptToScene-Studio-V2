<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

defineOptions({ name: 'AssetLightbox' })

const props = defineProps({
  scene: { type: Object, required: true },
  files: { type: Array, required: true },
  initialIndex: { type: Number, default: 0 },
})

const emit = defineEmits(['close'])

const currentIndex = ref(props.initialIndex)

const currentFile = computed(() => props.files[currentIndex.value] || props.files[0])
const total = computed(() => props.files.length)

function fileSrc(file) {
  if (file.startsWith('http')) return file
  return `/output/animator/${file}`
}

function isImageFile(file) {
  const ext = file.split('.').pop().toLowerCase()
  return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif'].includes(ext)
}

function isVideoFile(file) {
  const ext = file.split('.').pop().toLowerCase()
  return ['mp4', 'webm', 'mov'].includes(ext)
}

function prev() {
  if (currentIndex.value > 0) currentIndex.value--
  else currentIndex.value = total.value - 1
}

function next() {
  if (currentIndex.value < total.value - 1) currentIndex.value++
  else currentIndex.value = 0
}

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
}

function onBackdropClick(e) {
  if (e.target === e.currentTarget) emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.body.style.overflow = 'hidden'
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="lightbox-backdrop" @click="onBackdropClick">
    <div class="lightbox-container">
      <!-- Close button -->
      <button class="lightbox-close" @click="emit('close')">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>

      <!-- Navigation arrows -->
      <button v-if="total > 1" class="nav-arrow nav-prev" @click.stop="prev">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="15,18 9,12 15,6" />
        </svg>
      </button>
      <button v-if="total > 1" class="nav-arrow nav-next" @click.stop="next">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,6 15,12 9,18" />
        </svg>
      </button>

      <!-- Main display -->
      <div class="lightbox-main" @click.stop>
        <img
          v-if="isImageFile(currentFile)"
          :src="fileSrc(currentFile)"
          :key="currentFile"
          class="lightbox-media"
          alt=""
        />
        <video
          v-else-if="isVideoFile(currentFile)"
          :src="fileSrc(currentFile)"
          :key="'v-' + currentFile"
          class="lightbox-media"
          controls
          autoplay
        />
        <div v-else class="lightbox-fallback">
          <span>Unsupported file type</span>
        </div>
      </div>

      <!-- Counter -->
      <div v-if="total > 1" class="lightbox-counter">
        {{ currentIndex + 1 }} / {{ total }}
      </div>

      <!-- Thumbnail strip -->
      <div v-if="total > 1" class="thumbnail-strip" @click.stop>
        <button
          v-for="(file, i) in files"
          :key="i"
          class="thumbnail"
          :class="{ active: i === currentIndex }"
          @click="currentIndex = i"
        >
          <img
            v-if="isImageFile(file)"
            :src="fileSrc(file)"
            alt=""
            loading="lazy"
          />
          <div v-else class="thumb-placeholder">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M23 7l-7 5 7 5V7z" />
              <rect x="1" y="5" width="15" height="14" rx="2" />
            </svg>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lightbox-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-container {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 80px 100px;
}

/* ---- Close ---- */
.lightbox-close {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  color: #fff;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  transition: background 0.15s;
}

.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* ---- Navigation ---- */
.nav-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  color: #fff;
  cursor: pointer;
  padding: 12px;
  border-radius: 50%;
  transition: background 0.15s;
}

.nav-arrow:hover {
  background: rgba(255, 255, 255, 0.2);
}

.nav-prev {
  left: 20px;
}

.nav-next {
  right: 20px;
}

/* ---- Main media ---- */
.lightbox-main {
  max-width: 100%;
  max-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-media {
  max-width: 100%;
  max-height: calc(100vh - 200px);
  object-fit: contain;
  border-radius: 8px;
}

.lightbox-fallback {
  color: var(--text-secondary);
  font-size: 14px;
}

/* ---- Counter ---- */
.lightbox-counter {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(0, 0, 0, 0.4);
  padding: 4px 14px;
  border-radius: 12px;
}

/* ---- Thumbnails ---- */
.thumbnail-strip {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 6px;
  padding: 8px;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 10px;
  max-width: 90%;
  overflow-x: auto;
}

.thumbnail {
  width: 56px;
  height: 42px;
  border-radius: 6px;
  overflow: hidden;
  border: 2px solid transparent;
  cursor: pointer;
  padding: 0;
  background: rgba(255, 255, 255, 0.05);
  flex-shrink: 0;
  transition: border-color 0.15s;
}

.thumbnail.active {
  border-color: var(--accent);
}

.thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.4);
}
</style>
